from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

GENERIC_ACTIONS = {
    "a character advances the scene.",
    "the character moves forward.",
    "something happens.",
    "the scene continues.",
}


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _subject_from_visual(prompt: str) -> tuple[str | None, str]:
    """Extract a conservative named subject and its visual description."""
    match = re.search(r"\bSubject\s*:\s*([A-Z][A-Za-z0-9_' -]{0,35}?)(?:,|\.|\s+is\b|\s+wearing\b)(.*)$", prompt)
    if not match:
        return None, ""
    name = match.group(1).strip()
    if len(name.split()) > 3:
        return None, ""
    profile = match.group(2).strip(" ,.;")
    profile = re.split(r"\b(?:Environment|Setting|Camera|Lighting|Style|Composition)\s*:", profile, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ,.;")
    return name, profile


def _normalise_character_record(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str) and item.strip():
        return {"name": item.strip()}
    if not isinstance(item, dict):
        return None
    name = item.get("name") or item.get("character") or item.get("character_name") or item.get("full_name")
    if not name:
        return None
    record = dict(item)
    record["name"] = str(name).strip()
    aliases = {
        "appearance": ("visual_description", "look", "physical_description", "appearance_description"),
        "clothing": ("outfit", "costume", "clothes"),
        "voice": ("voice_description", "voice_traits"),
        "personality": ("traits", "personality_traits"),
        "age": ("character_age",),
    }
    for target, keys in aliases.items():
        if not record.get(target):
            for key in keys:
                if record.get(key) is not None:
                    record[target] = record[key]
                    break
    return record


def merge_character_bible(existing: list[Any], incoming: list[Any]) -> list[dict[str, Any]]:
    """Merge by case-insensitive name; do not erase established visual canon."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for source in (existing, incoming):
        for raw in source if isinstance(source, list) else []:
            item = _normalise_character_record(raw)
            if not item:
                continue
            key = item["name"].casefold()
            if key not in merged:
                merged[key] = {}
                order.append(key)
            # Non-empty new fields update the record; empty fields never erase canon.
            for field, value in item.items():
                if value not in (None, "", [], {}):
                    merged[key][field] = value
    return [merged[key] for key in order]


def build_character_bible(episode: dict[str, Any], memory: dict[str, Any]) -> list[dict[str, Any]]:
    records = merge_character_bible(
        memory.get("characters", []) if isinstance(memory.get("characters"), list) else [],
        episode.get("new_characters", []) if isinstance(episode.get("new_characters"), list) else [],
    )
    by_name = {x["name"].casefold(): x for x in records if x.get("name")}

    for scene in episode.get("scenes", []):
        prompt = _clean(scene.get("visual_prompt"))
        inferred, inferred_profile = _subject_from_visual(prompt)
        scene_names = list(scene.get("characters", []))
        if inferred and inferred.casefold() not in {n.casefold() for n in scene_names}:
            scene_names.append(inferred)
            scene["characters"] = scene_names
        for line in scene.get("dialogue", []):
            name = _clean(line.get("character"))
            if name and name.casefold() != "narrator" and name.casefold() not in {n.casefold() for n in scene_names}:
                scene_names.append(name)
        scene["characters"] = scene_names

        for name in scene_names:
            key = name.casefold()
            if key not in by_name:
                record = {"name": name, "first_seen_episode": episode.get("episode_number")}
                if inferred and inferred.casefold() == key and inferred_profile:
                    record["appearance"] = inferred_profile
                records.append(record)
                by_name[key] = record
            # Add a compact appearance anchor to prompts when there is canonical data.
            record = by_name[key]
            appearance = _clean(record.get("appearance"))
            clothing = _clean(record.get("clothing"))
            anchor_parts = [p for p in (appearance, clothing) if p]
            anchor = "; ".join(anchor_parts)
            if anchor and name.casefold() in prompt.casefold() and anchor.casefold() not in prompt.casefold():
                scene["visual_prompt"] = f"{prompt} Character continuity anchor for {name}: {anchor}."

    return records


def quality_issues(episode: dict[str, Any]) -> list[str]:
    """Deterministic production checks. These checks do not judge artistic taste."""
    issues: list[str] = []
    title = _clean(episode.get("title"))
    if len(title) < 3 or title.casefold().startswith("episode "):
        issues.append("Provide a distinctive episode title, not a placeholder.")
    summary = _clean(episode.get("story_summary"))
    if len(summary) < 100:
        issues.append("story_summary must explain the episode's cause, development and outcome in at least 100 characters.")

    scenes = episode.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 3:
        return issues + ["Provide at least 3 complete scenes."]

    seen_numbers: set[int] = set()
    prompts: list[str] = []
    for index, scene in enumerate(scenes, start=1):
        prefix = f"Scene {index}"
        number = scene.get("scene_number")
        if number in seen_numbers:
            issues.append(f"{prefix}: scene_number is duplicated.")
        seen_numbers.add(number)
        if number != index:
            issues.append(f"{prefix}: scene_number must be sequential; expected {index}.")

        location = _clean(scene.get("location"))
        if not location or location.casefold() in {"unspecified location", "unknown", "n/a", "not specified"}:
            issues.append(f"{prefix}: specify a concrete location and environment.")

        action = _clean(scene.get("action"))
        if len(action) < 25 or action.casefold() in GENERIC_ACTIONS:
            issues.append(f"{prefix}: action must describe a specific visible action and its story consequence.")

        visual = _clean(scene.get("visual_prompt"))
        if len(visual) < 100:
            issues.append(f"{prefix}: visual_prompt needs subject, action, environment, camera, lighting and style detail.")
        if visual:
            prompts.append(visual)

        if not scene.get("characters"):
            issues.append(f"{prefix}: identify the visible character(s); do not leave characters empty.")
        if len(scene.get("dialogue", [])) > 8:
            issues.append(f"{prefix}: keep dialogue to 8 lines or fewer for a short animation scene.")
        if not _clean(scene.get("camera")):
            issues.append(f"{prefix}: provide a camera direction.")
        if not _clean(scene.get("audio_prompt")):
            issues.append(f"{prefix}: provide sound and music direction.")

    # Detect copy-paste prompts without requiring scenes to be stylistically unrelated.
    for i in range(len(prompts)):
        for j in range(i + 1, len(prompts)):
            ratio = SequenceMatcher(None, prompts[i].casefold(), prompts[j].casefold()).ratio()
            if ratio >= 0.88:
                issues.append(f"Scenes {i + 1} and {j + 1}: visual prompts are too similar; give each scene a distinct visual composition/action.")
    if not _clean(episode.get("ending_hook")) or len(_clean(episode.get("ending_hook"))) < 25:
        issues.append("ending_hook must create a specific, earned reason to watch the next episode.")
    return issues
