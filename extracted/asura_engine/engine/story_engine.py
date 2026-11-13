import json
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, ValidationError

SYSTEM_PROMPT = """
You are ASURA ENGINE, an autonomous creative director for an original ongoing animated universe.
You have broad creative freedom: invent plots, characters, locations, civilizations, mysteries,
relationships, conflicts, abilities and surprising developments. Do not wait for daily ideas.
There is no predetermined plot or ending. Build the universe organically episode by episode.

Continuity is mandatory. Read the supplied memory carefully. Do not reset, contradict, or forget
established facts without a meaningful in-story explanation. Recurring characters retain
recognizable appearance, voice, personality and history. Keep the protagonist's established age
and identity consistent. Characters may enter, leave, change sides, be injured or die when
narratively justified. Keep the series understandable to international audiences through visual
storytelling and emotion. Create original material; do not imitate existing franchises,
characters, scripts or signature styles.

Create one complete episode suitable for production as cinematic 3D animation. Use short,
production-friendly scenes. Each scene should generally be 5–10 seconds and contain one clear
visual action. Provide detailed visual prompts, camera, lighting, environment, character
appearance, dialogue, sound design and continuity references. Do not claim that Google Flow has
generated anything; you only create prompts.

Return ONLY valid JSON with these exact top-level keys:
episode_number (integer), title (string), logline (string), previously_on (string),
story_summary (string), new_characters (array), character_updates (array), scenes (array),
ending_hook (string), next_episode_seeds (array), memory_update (object).
Each scene must contain: scene_number (integer), duration_seconds (integer), location (string),
characters (array of strings), action (string), dialogue (array of {character, line}), camera
(string), visual_prompt (string), audio_prompt (string), continuity_notes (string).
The memory_update must contain: series_title (string), world_state (object), characters (array),
open_mysteries (array), important_events (array), continuity_rules (array of strings), and
recent_episode_summaries (array of strings). Do not include next_episode_number; the application
sets that value safely.
Make the first episode an intriguing but comprehensible beginning, not an info dump.
"""


class DialogueLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    character: str
    line: str


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_number: int = Field(ge=1)
    duration_seconds: int = Field(ge=1, le=60)
    location: str
    characters: list[str]
    action: str
    dialogue: list[DialogueLine]
    camera: str
    visual_prompt: str
    audio_prompt: str
    continuity_notes: str


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_number: int = Field(ge=1)
    title: str
    logline: str
    previously_on: str
    story_summary: str
    new_characters: list[dict[str, Any]]
    character_updates: list[dict[str, Any]]
    scenes: list[Scene] = Field(min_length=1)
    ending_hook: str
    next_episode_seeds: list[str]
    memory_update: dict[str, Any]


class StoryEngine:
    def __init__(self) -> None:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Add it as a GitHub Actions repository secret."
            )
        self.client = genai.Client(api_key=key)
        self.model = os.getenv("STORY_MODEL", "gemini-3.8-flash").strip()
        if not self.model:
            raise RuntimeError("STORY_MODEL is empty. Set it to a supported Gemini model ID.")

    def generate_episode(self, memory: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Create the next episode using this canonical story memory. Preserve continuity. "
            "The required episode_number is "
            f"{int(memory.get('next_episode_number', 1))}.\n\n"
            "CANONICAL MEMORY:\n"
            + json.dumps(memory, ensure_ascii=False)
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                max_output_tokens=12000,
            ),
        )
        content = response.text
        if not content or not content.strip():
            raise RuntimeError("Gemini returned an empty response. No episode was saved.")
        try:
            raw = json.loads(content)
            episode = Episode.model_validate(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"Gemini response was not valid episode JSON: {exc}") from exc

        expected_number = int(memory.get("next_episode_number", 1))
        if episode.episode_number != expected_number:
            raise ValueError(
                f"Gemini returned episode {episode.episode_number}; "
                f"expected episode {expected_number}. No episode was saved."
            )
        return episode.model_dump(mode="json")
