from __future__ import annotations

import json
import os
import re
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from engine.quality import merge_character_bible

_EPISODE_RE = re.compile(r"^episode_(\d+)\.json$")
_PROMPT_RE = re.compile(r"^episode_(\d+)_flow_prompts\.json$")



@contextmanager
def generation_lock(root: Path):
    """Prevent two local processes from generating the same next episode."""
    lock_path = root / ".generation.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another ASURA generation process is already running; refusing a concurrent run.") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _numbered_files(folder: Path, pattern: re.Pattern[str]) -> dict[int, Path]:
    found: dict[int, Path] = {}
    if not folder.exists():
        return found
    for path in folder.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match:
            number = int(match.group(1))
            if number in found:
                raise RuntimeError(f"Duplicate numbered files for episode {number} in {folder}")
            found[number] = path
    return found


def _recover_prompt(episode: dict[str, Any], number: int, memory: dict[str, Any]) -> dict[str, Any]:
    scenes = episode.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError(
            f"Episode {number} exists but has no usable scenes; cannot safely rebuild its Flow prompts."
        )
    episode_memory = episode.get("memory_update")
    chars = memory.get("characters", [])
    if isinstance(episode_memory, dict) and isinstance(episode_memory.get("characters"), list):
        chars = merge_character_bible(
            chars if isinstance(chars, list) else [],
            episode_memory["characters"],
        )
    return {
        "series": memory.get("series_title", "THE OTHER SIDE"),
        "episode": number,
        "title": str(episode.get("title", f"Episode {number}")),
        "character_reference_notes": chars,
        "scenes": scenes,
    }


def reconcile_episode_history(root: Path, memory: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """
    Reconcile disk artifacts with story memory before generation.

    - Never overwrites an existing episode.
    - Recovers a missing Flow-prompt file from a completed episode JSON.
    - Refuses to guess when a prompt exists without its source episode.
    - Repairs stale memory from the newest saved episode's memory_update.
    - Chooses a new number greater than every existing episode/prompt and
      never lower than memory.next_episode_number.
    """
    episodes_dir = root / "episodes"
    prompts_dir = root / "prompts"
    episodes = _numbered_files(episodes_dir, _EPISODE_RE)
    prompts = _numbered_files(prompts_dir, _PROMPT_RE)

    prompt_only = sorted(set(prompts) - set(episodes))
    if prompt_only:
        numbers = ", ".join(str(n) for n in prompt_only)
        raise RuntimeError(
            "Flow prompt file(s) exist without matching episode JSON: "
            f"{numbers}. Refusing to overwrite or guess; inspect these artifacts first."
        )

    # Validate every saved episode and repair only the derived prompt artifact.
    loaded: dict[int, dict[str, Any]] = {}
    for number, path in sorted(episodes.items()):
        try:
            episode = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Cannot read saved episode {path}: {exc}") from exc
        if not isinstance(episode, dict):
            raise RuntimeError(f"Saved episode {path} is not a JSON object.")
        recorded_number = episode.get("episode_number", number)
        try:
            recorded_number = int(recorded_number)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Saved episode {path} has an invalid episode_number.") from exc
        if recorded_number != number:
            raise RuntimeError(
                f"Filename says Episode {number}, but JSON says Episode {recorded_number}: {path}"
            )
        loaded[number] = episode

        if number not in prompts:
            prompt_path = prompts_dir / f"episode_{number:04d}_flow_prompts.json"
            _atomic_json(prompt_path, _recover_prompt(episode, number, memory))
            prompts[number] = prompt_path
        else:
            try:
                prompt_data = json.loads(prompts[number].read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(f"Cannot read Flow prompt file {prompts[number]}: {exc}") from exc
            if not isinstance(prompt_data, dict) or int(prompt_data.get("episode", number)) != number:
                raise RuntimeError(f"Flow prompt file {prompts[number]} does not match Episode {number}.")

    latest_number = max(loaded, default=0)
    memory_next = memory.get("next_episode_number", 1)
    try:
        memory_next = int(memory_next)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("story_state.json next_episode_number must be an integer.") from exc
    if memory_next < 1:
        raise RuntimeError("story_state.json next_episode_number must be >= 1.")

    # If the episode exists but memory was not committed (e.g. interrupted run),
    # recover the latest canonical memory update from that saved episode.
    if latest_number and memory_next <= latest_number:
        latest = loaded[latest_number]
        update = latest.get("memory_update", {})
        if not isinstance(update, dict) or not update:
            raise RuntimeError(
                f"Story memory is behind Episode {latest_number}, but that episode has no usable memory_update. "
                "Refusing to continue with incomplete continuity."
            )
        if isinstance(update, dict):
            for key in (
                "world_state", "open_mysteries", "important_events",
                "continuity_rules", "recent_episode_summaries",
            ):
                value = update.get(key)
                if value is not None:
                    if key == "world_state" and isinstance(value, dict):
                        memory[key] = {**(memory.get(key, {}) if isinstance(memory.get(key), dict) else {}), **value}
                    elif isinstance(value, list):
                        memory[key] = value
            if isinstance(update.get("characters"), list):
                memory["characters"] = merge_character_bible(
                    memory.get("characters", []) if isinstance(memory.get("characters"), list) else [],
                    update["characters"],
                )
        summary = str(latest.get("story_summary", "")).strip()
        summaries = memory.get("recent_episode_summaries", [])
        if not isinstance(summaries, list):
            summaries = []
        summary_entry = f"Episode {latest_number}: {summary}" if summary else ""
        if summary_entry and summary_entry not in summaries:
            summaries.append(summary_entry)
        memory["recent_episode_summaries"] = summaries[-30:]
        memory["last_episode_title"] = latest.get("title", memory.get("last_episode_title"))
        memory["last_reconciled_episode"] = latest_number

    next_number = max(memory_next, latest_number + 1)
    memory["next_episode_number"] = next_number
    return memory, next_number
