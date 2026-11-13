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

    def generate_episode(self, memory: dict[str, Any]) -> dict[str, Any]:
        expected = int(memory.get("next_episode_number", 1))
        prompt = (
            f"Create episode number {expected}. Use this canonical memory as source of truth. "
            "Think independently and advance the story with meaningful cause and effect. "
            "Return the complete structured JSON episode.\n\nCANONICAL MEMORY:\n" +
            json.dumps(memory, ensure_ascii=False)
        )
        errors: list[str] = []
        for model in self.models:
            try:
                logger.info("Requesting episode %s using model %s", expected, model)
                content = self._request_one_model(model, prompt)
                raw = json.loads(content)
                episode = Episode.model_validate(raw)
                if episode.episode_number != expected:
                    raise ValueError(f"Model returned episode {episode.episode_number}; expected {expected}")
                logger.info("Episode %s generated successfully with %s", expected, model)
                result = episode.model_dump(mode="json")
                result["generation_model"] = model
                return result
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                # Invalid structured output is not a transient server error; try next configured model once.
                errors.append(f"{model}: invalid output: {exc}")
                logger.warning("Model %s produced invalid output; trying fallback", model)
            except Exception as exc:
                status = _status_code(exc)
                errors.append(f"{model}: HTTP/status {status or 'unknown'}: {str(exc)[:500]}")
                logger.error("Model %s failed: status=%s error=%s", model, status, str(exc)[:300])
                # Try next model for transient overload and model-not-found; do not hide auth/config errors.
                if status not in RETRYABLE_CODES and status not in {404}:
                    raise RuntimeError(f"Gemini request failed on {model}; not retrying other models. {exc}") from exc
        raise RuntimeError("All configured Gemini models failed. " + " | ".join(errors))
