from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import logging
import os

from dotenv import load_dotenv

from engine.story_engine import StoryEngine
from engine.memory import load_memory, save_memory
from engine.reconciliation import generation_lock, reconcile_episode_history

ROOT = Path(__file__).resolve().parent


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main() -> None:
    load_dotenv(ROOT / ".env")
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # OS-level lock complements the GitHub Actions concurrency group.
    with generation_lock(ROOT):
        memory_path = ROOT / "AI_BRAIN" / "story_state.json"
        memory = load_memory(memory_path)

        # Reconcile disk artifacts with canonical memory before choosing a number.
        memory, number = reconcile_episode_history(ROOT, memory)
        logging.info("Episode history reconciled; next episode number is %s", number)

        episode_path = ROOT / "episodes" / f"episode_{number:04d}.json"
        prompt_path = ROOT / "prompts" / f"episode_{number:04d}_flow_prompts.json"
        if episode_path.exists() or prompt_path.exists():
            raise FileExistsError(
                f"Episode {number} target already exists after reconciliation. "
                "Refusing to overwrite; inspect the existing files."
            )

        # Give the model the reconciled next number, not a stale value from disk.
        memory["next_episode_number"] = number
        episode = StoryEngine().generate_episode(memory)
        if int(episode.get("episode_number", -1)) != number:
            raise ValueError(
                f"Generated episode number {episode.get('episode_number')} does not match expected {number}; nothing saved."
            )

        update = episode["memory_update"]
        merged = {**memory, **update}
        merged["next_episode_number"] = number + 1
        merged["last_episode_title"] = episode["title"]
        merged["last_episode_generation_model"] = episode.get("generation_model")
        merged["last_updated_utc"] = datetime.now(timezone.utc).isoformat()

        for key, expected_type in {
            "world_state": dict,
            "characters": list,
            "open_mysteries": list,
            "important_events": list,
            "continuity_rules": list,
            "recent_episode_summaries": list,
        }.items():
            if not isinstance(merged.get(key), expected_type):
                raise ValueError(
                    f"memory_update field {key!r} must be {expected_type.__name__}; nothing saved"
                )

        summary = episode.get("story_summary", "").strip()
        summaries = merged["recent_episode_summaries"]
        if summary:
            entry = f"Episode {number}: {summary}"
            if entry not in summaries:
                summaries.append(entry)
        merged["recent_episode_summaries"] = summaries[-30:]

        # Write episode + prompts first. Canonical memory advances only after both writes succeed.
        write_json_atomic(episode_path, episode)
        write_json_atomic(
            prompt_path,
            {
                "series": merged.get("series_title", "THE OTHER SIDE"),
                "episode": number,
                "title": episode["title"],
                "character_reference_notes": merged.get("characters", []),
                "scenes": episode["scenes"],
            },
        )
        save_memory(memory_path, merged)

        logging.info("Created episode %s: %s", number, episode["title"])
        logging.info("Generation model: %s", episode.get("generation_model"))
        logging.info("Episode file: %s", episode_path)
        logging.info("Flow prompt file: %s", prompt_path)
        logging.info("Story memory advanced to episode %s", number + 1)
        logging.info(
            "NEXT: Flow generation and YouTube publishing are separate integrations; not executed by this story-only run."
        )


if __name__ == "__main__":
    main()
