import json
from pathlib import Path

import pytest

from engine.memory import load_memory
from engine.reconciliation import reconcile_episode_history


def _episode(number: int) -> dict:
    return {
        "episode_number": number,
        "title": f"Episode {number} title",
        "story_summary": f"A sufficiently detailed summary for episode {number}, with a meaningful event.",
        "scenes": [
            {"scene_number": 1, "duration_seconds": 6, "location": "Old station",
             "characters": ["Leo"], "action": "Leo opens the locked door.", "dialogue": [],
             "camera": "Wide shot", "visual_prompt": "Cinematic scene of Leo opening an old door.",
             "audio_prompt": "Metal creak", "continuity_notes": "Rain continues"}
        ],
        "memory_update": {
            "world_state": {"latest_event": f"episode {number}"},
            "characters": [{"name": "Leo", "appearance": "Dark hair"}],
            "open_mysteries": [], "important_events": [f"event {number}"],
            "continuity_rules": ["Preserve continuity"],
            "recent_episode_summaries": [f"Episode {number}: saved summary"],
        },
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_stale_memory_advances_from_existing_episode_and_rebuilds_prompt(tmp_path: Path):
    _write(tmp_path / "episodes" / "episode_0001.json", _episode(1))
    memory = load_memory(tmp_path / "AI_BRAIN" / "story_state.json")

    reconciled, next_number = reconcile_episode_history(tmp_path, memory)

    assert next_number == 2
    assert reconciled["next_episode_number"] == 2
    assert reconciled["world_state"]["latest_event"] == "episode 1"
    prompt = json.loads((tmp_path / "prompts" / "episode_0001_flow_prompts.json").read_text())
    assert prompt["episode"] == 1
    assert prompt["scenes"][0]["characters"] == ["Leo"]


def test_uses_maximum_existing_number_and_memory_number(tmp_path: Path):
    _write(tmp_path / "episodes" / "episode_0001.json", _episode(1))
    _write(tmp_path / "episodes" / "episode_0003.json", _episode(3))
    memory = load_memory(tmp_path / "AI_BRAIN" / "story_state.json")
    memory["next_episode_number"] = 2

    _, next_number = reconcile_episode_history(tmp_path, memory)

    assert next_number == 4


def test_never_moves_backwards_when_memory_is_ahead(tmp_path: Path):
    _write(tmp_path / "episodes" / "episode_0001.json", _episode(1))
    memory = load_memory(tmp_path / "AI_BRAIN" / "story_state.json")
    memory["next_episode_number"] = 5

    _, next_number = reconcile_episode_history(tmp_path, memory)

    assert next_number == 5


def test_prompt_without_episode_fails_safely(tmp_path: Path):
    _write(tmp_path / "prompts" / "episode_0002_flow_prompts.json", {"episode": 2, "scenes": []})
    memory = load_memory(tmp_path / "AI_BRAIN" / "story_state.json")

    with pytest.raises(RuntimeError, match="without matching episode JSON"):
        reconcile_episode_history(tmp_path, memory)


def test_corrupt_episode_fails_safely(tmp_path: Path):
    path = tmp_path / "episodes" / "episode_0001.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    memory = load_memory(tmp_path / "AI_BRAIN" / "story_state.json")

    with pytest.raises(RuntimeError, match="Cannot read saved episode"):
        reconcile_episode_history(tmp_path, memory)


def test_generation_lock_rejects_second_process_lock(tmp_path: Path):
    from engine.reconciliation import generation_lock

    with generation_lock(tmp_path):
        with pytest.raises(RuntimeError, match="already running"):
            with generation_lock(tmp_path):
                pass
