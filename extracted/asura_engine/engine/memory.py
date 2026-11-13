from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_MEMORY: dict[str, Any] = {
    "series_title": "THE OTHER SIDE",
    "series_format": "ongoing cinematic 3D animated series mixing a recognizable real world with an original fantasy world",
    "protagonist": {"age": 24, "identity": "to be organically established in Episode 1"},
    "creative_policy": "high creative freedom; no fixed plot, no fixed ending, preserve continuity and originality",
    "next_episode_number": 1,
    "world_state": {"real_world": "modern, globally recognizable everyday life", "fantasy_world": "unknown; discover organically through the story"},
    "characters": [],
    "open_mysteries": [],
    "important_events": [],
    "continuity_rules": [
        "Keep recurring characters recognizably consistent in face, age, body, clothing logic, voice, personality and history.",
        "Preserve cause and effect. Do not reset the story between episodes.",
        "Invent new characters, places, factions, powers and conflicts when they serve the story.",
        "Characters may leave, return, change sides, be injured or die only when narratively justified.",
        "Do not force a predetermined ending; let the universe evolve organically.",
        "Make the story understandable internationally through visual storytelling and universal emotions.",
        "Do not copy existing franchises, characters, scenes, scripts or signature styles."
    ],
    "recent_episode_summaries": [],
    "last_episode_title": None,
    "last_updated_utc": None
}

def load_memory(path: Path) -> dict[str, Any]:
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_MEMORY))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Story memory must be a JSON object")
    # Keep required top-level fields if a previous model response omitted one.
    merged = json.loads(json.dumps(DEFAULT_MEMORY))
    merged.update(data)
    for key, expected in {
        "next_episode_number": int, "world_state": dict, "characters": list,
        "open_mysteries": list, "important_events": list,
        "continuity_rules": list, "recent_episode_summaries": list,
    }.items():
        if not isinstance(merged.get(key), expected):
            raise ValueError(f"Story memory field {key!r} must be {expected.__name__}")
    return merged

def save_memory(path: Path, memory: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
