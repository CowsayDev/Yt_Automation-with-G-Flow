# ASURA Engine — Gemini-powered animated-series story starter

This repository generates one continuity-aware episode and scene-level Google Flow prompts per day using the Gemini API. It runs on GitHub Actions; no VPS is required.

## What works
- Gemini-powered episode writing with JSON parsing and Pydantic validation.
- Persistent JSON story memory, including the protagonist age and continuity rules.
- Scene-by-scene visual and audio prompts for later use in Google Flow.
- Daily GitHub Actions schedule (12:00 PM IST / 06:30 UTC) and manual runs.
- Episode JSON and prompts committed to the repository.

## Not implemented yet
Google Flow browser automation/video generation and YouTube publishing are not implemented in this starter. Do not assume an episode JSON means a video has been rendered or uploaded. Google Flow UI automation can break when its UI changes and may require manual login verification; never bypass CAPTCHA or security controls.

## Setup
1. Upload these files to a GitHub repository.
2. In **Settings → Secrets and variables → Actions → Secrets**, add `GEMINI_API_KEY`.
3. Optionally add repository variable `STORY_MODEL` with a model ID available to your Gemini API project. Default: `gemini-3.8-flash`.
4. In **Actions**, run **ASURA Engine - Daily Episode → Run workflow** to test.
5. Inspect `episodes/`, `prompts/`, and `AI_BRAIN/story_state.json`.

## Local test
Copy `.env.example` to `.env`, add your key, then run:

```bash
python -m pip install -r requirements.txt
python main.py
```

Never commit `.env` or API keys. Gemini free-tier availability, model access, and quotas depend on the Google AI Studio project and its current limits. See https://ai.google.dev/gemini-api/docs/pricing and https://ai.google.dev/gemini-api/docs/rate-limits.

The schedule creates story text and prompts only. GitHub Actions minutes/storage and Gemini quotas still apply.
