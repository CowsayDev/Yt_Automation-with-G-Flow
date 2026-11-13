import json
from pathlib import Path
from typing import Any


def load_memory(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "series_title": "THE OTHER SIDE",
            "format": "ongoing cinematic 3D animated series; fantasy and real-world blend",
            "protagonist_age": 24,
            "creative_policy": "high creative freedom; preserve established continuity",
            "next_episode_number": 1,
            "world_state": {},
            "characters": [],
            "open_mysteries": [],
            "important_events": [],
            "continuity_rules": [
                "Do not contradict established events without an in-story explanation.",
                "Keep recurring character appearance and personality stable.",
                "New characters and locations may be invented whenever useful.",
                "Do not force a predetermined ending.",
            ],
            "recent_episode_summaries": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Story memory JSON is corrupted at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Story memory must be a JSON object.")
    if not isinstance(data.get("next_episode_number"), int) or data["next_episode_number"] < 1:
        raise ValueError("Story memory next_episode_number must be a positive integer.")
    return data


def save_memory(path: Path, memory: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)
