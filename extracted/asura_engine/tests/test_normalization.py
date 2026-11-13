from engine.story_engine import normalize_episode_payload, Episode


def test_normalizes_common_gemini_field_names():
    memory = {
        "next_episode_number": 1,
        "recent_episode_summaries": [],
        "world_state": {},
        "characters": [],
        "open_mysteries": [],
        "important_events": [],
        "continuity_rules": [],
        "recent_episode_summaries": [],
    }
    raw = {
        "episode_number": 1,
        "episode_title": "The Threshold at Midnight",
        "synopsis": "A young man discovers a hidden threshold.",
        "next_episode_hook": "The door opens by itself.",
        "scenes": [
            {
                "scene_number": i,
                "duration": 8,
                "location": "A rainy street",
                "action_description": f"Kaelen moves toward the door in scene {i}.",
                "dialogue": [{"speaker": "Kaelen", "line": "What is that?"}],
            }
            for i in range(1, 4)
        ],
    }
    normalized = normalize_episode_payload(raw, memory, 1)
    episode = Episode.model_validate(normalized)
    assert episode.title == "The Threshold at Midnight"
    assert episode.scenes[0].dialogue[0].character == "Kaelen"
    assert episode.memory_update["world_state"] == {}
