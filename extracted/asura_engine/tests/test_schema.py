from engine.story_engine import Episode

def test_episode_schema_accepts_minimal_valid_episode():
    episode = Episode.model_validate({
        "episode_number": 1, "title": "First Signal", "logline": "A signal appears.",
        "previously_on": "", "story_summary": "A signal appears in the city.",
        "new_characters": [], "character_updates": [],
        "scenes": [{"scene_number": 1, "duration_seconds": 6, "location": "City",
                    "characters": [], "action": "A light flickers.", "dialogue": [],
                    "camera": "Wide shot", "visual_prompt": "A cinematic 3D city at dusk, one light flickers.",
                    "audio_prompt": "Low hum", "continuity_notes": "Opening scene"},
                   {"scene_number": 2, "duration_seconds": 6, "location": "Street",
                    "characters": [], "action": "A person looks up.", "dialogue": [],
                    "camera": "Close-up", "visual_prompt": "A cinematic close-up of a person looking up at a glowing sky.",
                    "audio_prompt": "Rising tone", "continuity_notes": "Same evening"},
                   {"scene_number": 3, "duration_seconds": 6, "location": "Rooftop",
                    "characters": [], "action": "A shadow moves.", "dialogue": [],
                    "camera": "Slow push-in", "visual_prompt": "A mysterious shadow crosses a rooftop under blue moonlight.",
                    "audio_prompt": "Deep impact", "continuity_notes": "Ending hook"}],
        "ending_hook": "A second signal answers.", "next_episode_seeds": ["Find the source"],
        "memory_update": {"world_state": {}, "characters": [], "open_mysteries": [],
                          "important_events": [], "continuity_rules": [], "recent_episode_summaries": []}
    })
    assert episode.episode_number == 1
