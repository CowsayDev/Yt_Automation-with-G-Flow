from pathlib import Path
from datetime import datetime, timezone
import json
import os

from dotenv import load_dotenv

from engine.story_engine import StoryEngine
from engine.memory import load_memory, save_memory

ROOT = Path(__file__).resolve().parent


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def main() -> None:
    load_dotenv(ROOT / ".env")
    memory_path = ROOT / "AI_BRAIN" / "story_state.json"
    memory = load_memory(memory_path)
    number = int(memory.get("next_episode_number", 1))
    if number < 1:
        raise ValueError("story_state.json next_episode_number must be >= 1")

    episode_path = ROOT / "episodes" / f"episode_{number:04d}.json"
    prompt_path = ROOT / "prompts" / f"episode_{number:04d}_flow_prompts.json"
    if episode_path.exists() or prompt_path.exists():
        raise FileExistsError(
            f"Episode {number} output already exists. Check repository memory/files before retrying; "
            "refusing to overwrite an existing episode."
        )

    engine = StoryEngine()
    episode = engine.generate_episode(memory)
    updated = episode["memory_update"]

    # Keep canonical fields even if the model accidentally omits one.
    merged_memory = {**memory, **updated}
    merged_memory["next_episode_number"] = number + 1
    merged_memory["last_episode_title"] = episode["title"]
    merged_memory["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

    required_memory_fields = {
        "world_state": dict,
        "characters": list,
        "open_mysteries": list,
        "important_events": list,
        "continuity_rules": list,
        "recent_episode_summaries": list,
    }
    for field, expected_type in required_memory_fields.items():
        if not isinstance(merged_memory.get(field), expected_type):
            raise ValueError(
                f"memory_update field '{field}' must be {expected_type.__name__}; "
                "nothing was saved."
            )

    summary = episode.get("story_summary", "").strip()
    if summary:
        summaries = merged_memory["recent_episode_summaries"]
        if not summaries or summaries[-1] != summary:
            summaries.append(f"Episode {number}: {summary}")
        merged_memory["recent_episode_summaries"] = summaries[-20:]

    # Save episode and prompts first; update canonical memory last.
    write_json_atomic(episode_path, episode)
    write_json_atomic(prompt_path, {"episode": number, "scenes": episode["scenes"]})
    save_memory(memory_path, merged_memory)

    print(f"Created episode {number}: {episode['title']}")
    print(f"Episode: {episode_path}")
    print(f"Flow prompts: {prompt_path}")
    print("Google Flow video generation and YouTube upload are not implemented yet.")


if __name__ == "__main__":
    main()
