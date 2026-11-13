# Google Flow stage — not yet automated

The Story Engine writes scene-by-scene prompts to `prompts/episode_NNNN_flow_prompts.json`.
This repository version deliberately does not pretend that Flow has been automated or tested.
Google's official Flow help documents the web UI workflow and notes that available features,
models, credits and regions vary. Browser UI selectors and login challenges can change.

Before enabling unattended Playwright:
- Verify that your account/region/plan permits the intended generation.
- Use an account-authenticated browser state only if permitted by Google's terms and policies.
- Never bypass CAPTCHA, unusual-activity checks, MFA or account security.
- Store any auth state only in encrypted GitHub Secrets; never commit cookies or state files.
- Test manually with one prompt first; confirm generated MP4 download and stable character references.
- Treat UI automation as fragile and stop for human review if a security challenge appears.

Official help: https://support.google.com/flow/answer/16353334
