# ASURA Engine — closed-loop story generation core

This update hardens the autonomous story-generation loop: canonical persistent memory, strict
episode validation, bounded retry with exponential backoff + jitter, model fallback, atomic writes,
unique episode numbering, and GitHub Actions persistence.

## Current working scope
- Gemini text generation for one continuity-aware episode per run.
- Model retry/fallback: primary is `STORY_MODEL`; fallbacks are configured in the workflow.
- Structured JSON validation before saving.
- Story memory only advances after episode and prompt files are written successfully.
- Daily workflow at 12:00 PM Asia/Kolkata and manual dispatch.

## Not yet in this build
Google Flow browser generation and YouTube upload are NOT automated. The two integration folders
contain the safe integration requirements only. Do not assume an MP4 is generated or published.
The Flow UI can change and Google may require login/MFA/CAPTCHA; automation must not bypass security.

## GitHub setup
Repository Secrets:
- `GEMINI_API_KEY`: your Google AI Studio API key.
- `STORY_MODEL`: `gemini-3.7-flash` (or another model available to your API project).

The workflow configures fallbacks `gemini-3.8-flash,gemini-3.5-flash-lite`. Model access and capacity
are project/tier dependent; fallback does not guarantee availability or zero cost.

## Update existing repository
The existing project is under `extracted/asura_engine/`. Replace that folder's files with the
contents of this ZIP's `asura_engine/` folder. Keep the repository-root workflow that runs from
`extracted/asura_engine`; do not create a second competing daily workflow inside the nested folder.

## Run locally
```bash
python -m pip install -r requirements.txt
cp .env.example .env  # edit locally; never commit .env
python main.py
```

## Story quality control (v3)

The story engine now normalizes common Gemini JSON aliases, builds a persistent character bible from explicit character records and named visual subjects, and runs deterministic scene-quality checks before saving an episode. If output fails schema or production checks, it makes one bounded repair request to the same model before moving to the configured fallback model. Story memory is still written only after a validated episode and its Flow prompt JSON are generated.

Quality checks include concrete locations, specific visible actions, named visible characters, detailed scene prompts, sequential scene numbering, and distinct visual prompts. These checks are production guardrails, not a guarantee of artistic quality or live API availability.
