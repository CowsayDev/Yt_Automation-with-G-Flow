import json
from pathlib import Path
from engine.memory import load_memory, save_memory

def test_default_memory_and_atomic_save(tmp_path: Path):
    path = tmp_path / "story_state.json"
    data = load_memory(path)
    assert data["next_episode_number"] == 1
    save_memory(path, data)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["protagonist"]["age"] == 24
