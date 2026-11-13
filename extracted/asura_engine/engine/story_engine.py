from __future__ import annotations
import json
import logging
import os
import random
import time
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.quality import build_character_bible, merge_character_bible, quality_issues

logger = logging.getLogger("asura.story")

SYSTEM_PROMPT = r"""
You are ASURA ENGINE: an autonomous showrunner, story architect, screenwriter and animation director.
You have broad creative freedom. There is no user-supplied plot outline and no predetermined ending.
Invent the plot, characters, relationships, places, fantasy rules, mysteries, conflicts, reversals,
comedy, action and emotional turns yourself. Keep the story original and suitable for a worldwide audience.

SERIES FOUNDATION (only fixed anchors):
- Series title: THE OTHER SIDE.
- Genre: cinematic 3D animation; real-world + fantasy-world blend.
- Main protagonist is 24 years old unless the canonical memory explicitly changes this through a story event.
- Everything else may be discovered and invented organically.

CONTINUITY IS A HARD REQUIREMENT:
- Treat the supplied memory as canonical truth.
- Continue from the latest event; never restart or retell the same episode.
- Preserve recurring character identity, visual description, personality, voice traits, relationships,
  injuries, possessions and current location unless the plot explains a change.
- Track who is present, absent, missing, dead, injured, allied or hostile.
- Resolve or deliberately advance existing mysteries; create new mysteries when useful.
- Update the world state and character records after every episode.
- If memory contains a previous-episode hook or seeds, consider them but you are not forced to use them.

PRODUCTION REQUIREMENTS:
- Write one complete next episode, with 5–10 second production-friendly scenes.
- Each scene must describe one coherent visual action, not a montage of unrelated actions.
- Keep the same character appearance across scenes. Repeat compact character visual anchors in every
  relevant visual_prompt so an image/video model can preserve identity.
- Visual prompts must specify subject, action, environment, framing/camera, lighting, style,
  composition and continuity anchors. Avoid vague prompts such as "same character as before" alone.
- Dialogue should be short and natural. Do not rely on on-screen text to explain key plot points.
- Every scene must use these exact keys: scene_number, duration_seconds, location, characters, action,
  dialogue, camera, visual_prompt, audio_prompt, continuity_notes.
- Every scene must name a concrete location, list at least one visible character, and describe one specific
  visible action with a consequence. Never use empty characters arrays or generic placeholder actions.
- Each dialogue item must use exactly {"character": "Name", "line": "Spoken words"}; use Narrator only
  for voiceover, not as a substitute for naming visible characters.
- Each new recurring character must have a profile with name, age, appearance, clothing, voice,
  personality and any distinctive prop. Keep those details stable in later episodes.
- Every visual_prompt must be scene-specific and include subject identity, visible action, environment,
  framing/camera, lighting, composition and cinematic 3D animation style. Do not copy the same prompt
  across scenes and do not rely only on the phrase "same character as before".
- memory_update must contain world_state (object), characters (array of character profiles),
  open_mysteries (array), important_events (array), continuity_rules (array), and
  recent_episode_summaries (array). Preserve established canon; do not erase prior characters.
- End with a compelling but earned hook that leads into the next episode.
- Do not claim any video has been generated. You only write story and production prompts.
- Do not imitate a named creator, existing franchise, or living artist's distinctive style.

Return ONLY valid JSON matching the schema enforced by the application. No Markdown fences.
"""

class DialogueLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    character: str
    line: str

class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_number: int = Field(ge=1)
    duration_seconds: int = Field(ge=3, le=15)
    location: str
    characters: list[str]
    action: str
    dialogue: list[DialogueLine]
    camera: str
    visual_prompt: str = Field(min_length=20)
    audio_prompt: str
    continuity_notes: str

class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_number: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=120)
    logline: str
    previously_on: str
    story_summary: str
    new_characters: list[dict[str, Any]]
    character_updates: list[dict[str, Any]]
    scenes: list[Scene] = Field(min_length=3, max_length=24)
    ending_hook: str
    next_episode_seeds: list[str]
    memory_update: dict[str, Any]



def _first(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return default

def normalize_episode_payload(raw: dict[str, Any], memory: dict[str, Any], expected: int) -> dict[str, Any]:
    """Map common model aliases to the strict internal episode contract."""
    if not isinstance(raw, dict):
        raise ValueError("Gemini episode response must be a JSON object")

    title = _first(raw, "title", "episode_title", "name", default=f"Episode {expected}")
    summary = _first(raw, "story_summary", "synopsis", "summary", "episode_summary", default="")
    scenes_in = _first(raw, "scenes", "sequence", "shots", "story_scenes", default=[])
    if not isinstance(scenes_in, list):
        raise ValueError("Gemini response scenes must be a list")

    scenes: list[dict[str, Any]] = []
    for index, item in enumerate(scenes_in, start=1):
        if not isinstance(item, dict):
            continue
        dialogue_in = _first(item, "dialogue", "dialog", "lines", "dialogue_lines", default=[])
        dialogue: list[dict[str, str]] = []
        if isinstance(dialogue_in, list):
            for line in dialogue_in:
                if isinstance(line, str):
                    dialogue.append({"character": "Narrator", "line": line.strip()})
                elif isinstance(line, dict):
                    character = _first(line, "character", "speaker", "name", "character_name", default="Narrator")
                    text = _first(line, "line", "text", "dialogue", "content", "spoken_text", default="")
                    if text:
                        dialogue.append({"character": str(character).strip(), "line": str(text).strip()})

        chars = _first(item, "characters", "characters_present", "cast", "character_names", default=[])
        if isinstance(chars, dict):
            chars = list(chars.keys())
        if not isinstance(chars, list):
            chars = [str(chars)] if chars else []
        chars = [str(x.get("name") or x.get("character") or x) if isinstance(x, dict) else str(x) for x in chars]
        chars = [x.strip() for x in chars if x.strip()]
        for line in dialogue:
            if line["character"].casefold() != "narrator" and line["character"].casefold() not in {x.casefold() for x in chars}:
                chars.append(line["character"])

        location = str(_first(item, "location", "setting", "environment", "place", default="")).strip()
        action = str(_first(item, "action", "action_description", "beat", "description", "what_happens", default="")).strip()
        visual = str(_first(item, "visual_prompt", "video_prompt", "image_prompt", "visual_description", "prompt", default="")).strip()
        if not visual:
            visual = (
                f"Cinematic 3D animated scene. Visible action: {action or 'A specific character action must be supplied'}; "
                f"environment: {location or 'location must be supplied'}. Show expressive character acting, "
                "clear foreground and background separation, cinematic composition, detailed lighting and coherent motion."
            )
        if not location and visual:
            import re
            match = re.search(r"\b(?:Location|Setting|Environment)\s*:\s*([^.;]+)", visual, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
        if not action and visual:
            action = str(_first(item, "visual_action", default="")).strip()
        if not chars and visual:
            import re
            match = re.search(r"\bSubject\s*:\s*([A-Z][A-Za-z0-9_' -]{0,35}?)(?:,|\.|\s+is\b|\s+wearing\b)", visual)
            if match:
                chars = [match.group(1).strip()]

        scenes.append({
            "scene_number": int(_first(item, "scene_number", "number", "index", default=index)),
            "duration_seconds": max(3, min(15, int(_first(item, "duration_seconds", "duration", "seconds", default=8)))),
            "location": location,
            "characters": chars,
            "action": action,
            "dialogue": dialogue,
            "camera": str(_first(item, "camera", "camera_direction", "shot", "framing", default="")).strip(),
            "visual_prompt": visual,
            "audio_prompt": str(_first(item, "audio_prompt", "sound_prompt", "audio", "sound_design", default="")).strip(),
            "continuity_notes": str(_first(item, "continuity_notes", "continuity", "continuity_anchor", default="")).strip(),
        })

    if len(scenes) < 3:
        raise ValueError(f"Gemini returned only {len(scenes)} usable scenes; at least 3 are required")

    supplied_memory = raw.get("memory_update")
    if not isinstance(supplied_memory, dict):
        supplied_memory = {}
    memory_update = dict(supplied_memory)
    world_update = _first(memory_update, "world_state", "world_state_update", default=_first(raw, "world_state_update", default=memory.get("world_state", {})))
    if not isinstance(world_update, dict):
        world_update = memory.get("world_state", {})
    memory_update["world_state"] = {**(memory.get("world_state", {}) if isinstance(memory.get("world_state"), dict) else {}), **world_update}

    new_characters = _first(raw, "new_characters", "characters_introduced", "new_character_profiles", default=[])
    if not isinstance(new_characters, list):
        new_characters = [new_characters] if new_characters else []
    character_updates = _first(raw, "character_updates", "character_changes", "character_state_changes", default=[])
    if not isinstance(character_updates, list):
        character_updates = [character_updates] if character_updates else []

    memory_characters = _first(memory_update, "characters", "character_roster", default=_first(raw, "characters_present", "character_roster", default=[]))
    if not isinstance(memory_characters, list):
        memory_characters = [memory_characters] if memory_characters else []
    memory_update["characters"] = merge_character_bible(
        memory.get("characters", []) if isinstance(memory.get("characters"), list) else [],
        [*memory_characters, *new_characters],
    )

    for key, aliases in {
        "open_mysteries": ("open_mysteries", "mysteries"),
        "important_events": ("important_events", "key_events", "events"),
        "continuity_rules": ("continuity_rules", "canon_rules"),
        "recent_episode_summaries": ("recent_episode_summaries",),
    }.items():
        value = _first(memory_update, *aliases, default=_first(raw, *aliases, default=memory.get(key, [])))
        memory_update[key] = value if isinstance(value, list) else [value] if value else memory.get(key, [])

    seeds = _first(raw, "next_episode_seeds", "next_episode_hook", "next_episode_hooks", "future_story_seeds", default=[])
    if isinstance(seeds, str):
        seeds = [seeds]
    if not isinstance(seeds, list):
        seeds = []

    normalized = {
        "episode_number": int(_first(raw, "episode_number", "episode", "number", default=expected)),
        "title": str(title).strip(),
        "logline": str(_first(raw, "logline", "premise", "one_line_hook", default=summary[:300])).strip(),
        "previously_on": str(_first(raw, "previously_on", "recap", "previous_episode_recap", default=(memory.get("recent_episode_summaries") or [""])[-1] if memory.get("recent_episode_summaries") else "The story begins.")).strip(),
        "story_summary": str(summary).strip(),
        "new_characters": [x for x in (new_characters) if isinstance(x, (dict, str))],
        "character_updates": [x for x in character_updates if isinstance(x, (dict, str))],
        "scenes": scenes,
        "ending_hook": str(_first(raw, "ending_hook", "next_episode_hook", "next_episode_teaser", "cliffhanger", default="")).strip(),
        "next_episode_seeds": [str(x) for x in seeds],
        "memory_update": memory_update,
    }
    normalized["new_characters"] = merge_character_bible([], normalized["new_characters"])
    normalized["memory_update"]["characters"] = merge_character_bible(
        normalized["memory_update"].get("characters", []),
        build_character_bible(normalized, memory),
    )
    return normalized

RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}

def _status_code(exc: Exception) -> int | None:
    for attr in ("code", "status_code", "http_status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    text = str(exc)
    for code in RETRYABLE_CODES:
        if str(code) in text:
            return code
    if "UNAVAILABLE" in text:
        return 503
    if "RESOURCE_EXHAUSTED" in text or "TOO MANY REQUESTS" in text.upper():
        return 429
    return None

class StoryEngine:
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Add it as a GitHub Actions repository secret.")
        # Disable the SDK's hidden retry loop so our bounded retry/fallback policy is the only retry layer.
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=1)
            ),
        )
        primary = os.getenv("STORY_MODEL", "gemini-3.7-flash").strip()
        if not primary:
            raise RuntimeError("STORY_MODEL is empty. Set it as a repository secret or workflow variable.")
        fallbacks = [x.strip() for x in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.8-flash,gemini-3.5-flash-lite").split(",") if x.strip()]
        # Preserve order and remove duplicates; primary always comes first.
        self.models = list(dict.fromkeys([primary, *fallbacks]))
        self.max_retries = max(1, min(int(os.getenv("MAX_RETRIES_PER_MODEL", "2")), 3))
        self.base_delay = max(1.0, float(os.getenv("BASE_RETRY_SECONDS", "3")))
        self.max_delay = max(self.base_delay, float(os.getenv("MAX_RETRY_SECONDS", "30")))

    def _request_one_model(self, model: str, prompt: str) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        max_output_tokens=12000,
                    ),
                )
                text = response.text
                if not text or not text.strip():
                    raise RuntimeError(f"Model {model} returned an empty response")
                return text
            except Exception as exc:
                last_error = exc
                status = _status_code(exc)
                if status not in RETRYABLE_CODES or attempt >= self.max_retries:
                    raise
                delay = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
                delay += random.uniform(0, min(2.0, delay * 0.25))
                logger.warning("Transient Gemini error model=%s status=%s attempt=%s/%s; retrying in %.1fs",
                               model, status, attempt, self.max_retries, delay)
                time.sleep(delay)
        assert last_error is not None
        raise last_error

    def _parse_validate(self, content: str, memory: dict[str, Any], expected: int, model: str) -> dict[str, Any]:
        raw = json.loads(content)
        normalized = normalize_episode_payload(raw, memory, expected)
        episode = Episode.model_validate(normalized)
        if episode.episode_number != expected:
            raise ValueError(f"Model returned episode {episode.episode_number}; expected {expected}")
        result = episode.model_dump(mode="json")
        result["generation_model"] = model
        issues = quality_issues(result)
        if issues:
            raise QualityValidationError(issues, result)
        return result

    def generate_episode(self, memory: dict[str, Any]) -> dict[str, Any]:
        expected = int(memory.get("next_episode_number", 1))
        prompt = (
            f"Create episode number {expected}. Use this canonical memory as source of truth. "
            "Think independently and advance the story with meaningful cause and effect. "
            "Every scene MUST have a specific named location, specific visible action, non-empty character list, "
            "distinct visual prompt, camera direction, audio direction and continuity notes. "
            "Never use placeholders such as 'Unspecified location' or 'A character advances the scene'. "
            "Include a compact character profile for every newly introduced recurring character. "
            "Return complete structured JSON.\n\nCANONICAL MEMORY:\n" +
            json.dumps(memory, ensure_ascii=False)
        )
        errors: list[str] = []
        for model in self.models:
            try:
                logger.info("Requesting episode %s using model %s", expected, model)
                content = self._request_one_model(model, prompt)
                try:
                    return self._parse_validate(content, memory, expected, model)
                except (json.JSONDecodeError, ValidationError, ValueError) as first_error:
                    issues = first_error.issues if isinstance(first_error, QualityValidationError) else [str(first_error)]
                    logger.warning("Model %s output needs repair: %s", model, "; ".join(issues)[:900])
                    repair_prompt = (
                        "Repair the episode JSON below. Keep its original story premise and creative intent, "
                        "but correct every listed schema and production-quality issue. Do not omit required fields. "
                        "Each scene must have a concrete location, a specific visible action, at least one visible "
                        "character, a distinct detailed visual prompt, camera, audio and continuity notes. "
                        "Do not use generic placeholders. Return ONLY the complete corrected JSON.\n\nISSUES:\n- " +
                        "\n- ".join(issues[:50]) +
                        "\n\nJSON TO REPAIR:\n" + content
                    )
                    # One bounded repair request per model; no unbounded self-correction loop.
                    repaired = self._request_one_model(model, repair_prompt)
                    try:
                        return self._parse_validate(repaired, memory, expected, model)
                    except (json.JSONDecodeError, ValidationError, ValueError) as repair_error:
                        repair_issues = repair_error.issues if isinstance(repair_error, QualityValidationError) else [str(repair_error)]
                        errors.append(f"{model}: repair failed: {'; '.join(repair_issues)[:900]}")
                        logger.warning("Model %s repair failed; trying configured fallback", model)
            except Exception as exc:
                status = _status_code(exc)
                errors.append(f"{model}: HTTP/status {status or 'unknown'}: {str(exc)[:500]}")
                logger.error("Model %s failed: status=%s error=%s", model, status, str(exc)[:300])
                if status not in RETRYABLE_CODES and status not in {404}:
                    # Validation failures are handled above; authentication/configuration errors should stop.
                    if not isinstance(exc, (json.JSONDecodeError, ValidationError, ValueError, QualityValidationError)):
                        raise RuntimeError(f"Gemini request failed on {model}; not retrying other models. {exc}") from exc
        raise RuntimeError("All configured Gemini models failed quality/schema checks. " + " | ".join(errors))


class QualityValidationError(ValueError):
    def __init__(self, issues: list[str], episode: dict[str, Any]):
        self.issues = issues
        self.episode = episode
        super().__init__("Episode quality checks failed: " + "; ".join(issues))

