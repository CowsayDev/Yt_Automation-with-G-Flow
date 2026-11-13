from engine.quality import build_character_bible, quality_issues
from engine.story_engine import Episode, normalize_episode_payload


def memory():
    return {
        "next_episode_number": 1,
        "world_state": {},
        "characters": [],
        "open_mysteries": [],
        "important_events": [],
        "continuity_rules": [],
        "recent_episode_summaries": [],
    }


def test_aliases_and_subject_name_are_normalized():
    raw = {
        "episode_number": 1,
        "episode_title": "The Glass Pavement",
        "synopsis": "A young man discovers that rain is falling upward in one forgotten street, revealing a hidden boundary between two worlds.",
        "ending_hook": "A second silhouette appears behind the glass and raises its hand.",
        "scenes": [
            {
                "scene_number": i,
                "duration_seconds": 8,
                "location": f"Old market street, scene {i}",
                "action_description": f"Leo follows a trail of glowing rain toward the locked arcade entrance in scene {i}.",
                "dialogue": [{"speaker": "Narrator", "text": "The rain moves against the wind."}],
                "visual_prompt": f"Cinematic 3D animation. Subject: Leo, a 24-year-old man with dark blond hair and a charcoal jacket. Scene {i}: he studies a different glowing symbol beside the wet arcade. Environment: abandoned market at night. Camera: slow push-in. Lighting: blue reflections and warm shop light. Style: detailed animated fantasy realism.",
                "camera": "Slow push-in from medium shot to close-up",
                "audio_prompt": "Rain ambience, distant traffic and a low mysterious pulse",
                "continuity_notes": "Leo keeps the same charcoal jacket and wet hair; the symbol grows brighter.",
            }
            for i in range(1, 4)
        ],
    }
    normalized = normalize_episode_payload(raw, memory(), 1)
    episode = Episode.model_validate(normalized)
    assert episode.title == "The Glass Pavement"
    assert episode.scenes[0].characters == ["Leo"]
    assert normalized["memory_update"]["characters"][0]["name"] == "Leo"


def test_quality_checker_rejects_placeholders():
    raw = {
        "episode_number": 1,
        "episode_title": "The Glass Pavement",
        "synopsis": "A young man discovers a hidden passage in the city and follows its strange light into a dangerous new world.",
        "scenes": [
            {
                "scene_number": i,
                "duration_seconds": 8,
                "location": "Unspecified location",
                "characters": [],
                "action_description": "A character advances the scene.",
                "dialogue": [],
                "visual_prompt": f"Cinematic 3D animation scene {i}.",
            }
            for i in range(1, 4)
        ],
    }
    normalized = normalize_episode_payload(raw, memory(), 1)
    issues = quality_issues(normalized)
    assert any("concrete location" in issue for issue in issues)
    assert any("specific visible action" in issue for issue in issues)
    assert any("visual_prompt" in issue for issue in issues)
    assert any("visible character" in issue for issue in issues)


def test_valid_episode_passes_quality_and_schema():
    raw = {
        "episode_number": 1,
        "title": "The Glass Pavement",
        "logline": "A strange rainstorm reveals a doorway beneath the city.",
        "previously_on": "The story begins.",
        "story_summary": "During an unusual storm, Leo notices rain rising from the pavement. He follows a line of blue light through an abandoned market and discovers a glass doorway beneath an old arcade. A shadow on the other side copies his movements, then reveals that it knows his name.",
        "new_characters": [{"name": "Leo", "age": 24, "appearance": "Dark blond hair, sharp jawline, charcoal field jacket", "personality": "Observant and cautious"}],
        "character_updates": [],
        "scenes": [
            {
                "scene_number": 1,
                "duration_seconds": 8,
                "location": "Rain-soaked apartment balcony overlooking the old city",
                "characters": ["Leo"],
                "action_description": "Leo catches a drop of rain rising from the balcony rail and watches it float toward the clouds.",
                "dialogue": [{"speaker": "Leo", "line": "Rain doesn't move like that."}],
                "camera": "Wide establishing shot, then a slow close-up on Leo's hand",
                "visual_prompt": "Cinematic 3D animation. Subject: Leo, a 24-year-old man with dark blond hair, sharp jawline and charcoal field jacket, catches a glowing raindrop rising from the balcony rail. Environment: rain-soaked apartment balcony above an old city at midnight. Camera: wide shot moving into close-up. Lighting: cool blue storm light with warm windows behind him. Style: richly detailed cinematic fantasy animation.",
                "audio_prompt": "Soft rain, distant thunder and a delicate rising glass tone",
                "continuity_notes": "Leo wears his charcoal field jacket; the first blue raindrop floats upward.",
            },
            {
                "scene_number": 2,
                "duration_seconds": 8,
                "location": "Narrow stone lane in the abandoned old market",
                "characters": ["Leo"],
                "action_description": "Leo follows a thin blue stream between shuttered stalls and sees it disappear beneath a cracked stone tile.",
                "dialogue": [{"speaker": "Leo", "line": "Where does it lead?"}],
                "camera": "Low tracking shot following the blue stream beside Leo's boots",
                "visual_prompt": "Cinematic 3D animation. Subject: Leo, a 24-year-old man with dark blond hair, sharp jawline and charcoal field jacket, follows a thin blue stream winding between shuttered market stalls. Environment: narrow wet stone lane in an abandoned old market. Camera: low tracking shot beside his boots. Lighting: reflected blue light and a single amber lantern. Style: richly detailed cinematic fantasy animation.",
                "audio_prompt": "Water trickle, distant metal creak and restrained suspense music",
                "continuity_notes": "Same jacket and hairstyle; the blue stream leads toward the cracked tile.",
            },
            {
                "scene_number": 3,
                "duration_seconds": 8,
                "location": "Underground chamber beneath the old arcade",
                "characters": ["Leo"],
                "action_description": "Leo lifts the cracked tile and reveals a glass doorway where a dark silhouette mirrors his raised hand.",
                "dialogue": [{"speaker": "Leo", "line": "Who's there?"}],
                "camera": "Over-the-shoulder shot pushing toward the glass doorway",
                "visual_prompt": "Cinematic 3D animation. Subject: Leo, a 24-year-old man with dark blond hair, sharp jawline and charcoal field jacket, lifts a cracked tile and freezes before a glass doorway as a silhouette mirrors his raised hand. Environment: hidden underground chamber beneath the old arcade. Camera: over-the-shoulder push-in toward the doorway. Lighting: pale cyan light from the glass and deep amber shadows. Style: richly detailed cinematic fantasy animation.",
                "audio_prompt": "Stone scrape, a low glass resonance and one distant heartbeat",
                "continuity_notes": "Leo remains outside the doorway; the mirrored silhouette has not crossed over.",
            },
        ],
        "ending_hook": "The silhouette writes Leo's name from the other side of the glass.",
        "next_episode_seeds": ["Who is the silhouette?", "Why does the doorway know Leo?"],
        "memory_update": {},
    }
    normalized = normalize_episode_payload(raw, memory(), 1)
    episode = Episode.model_validate(normalized).model_dump(mode="json")
    assert quality_issues(episode) == []
