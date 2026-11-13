# YouTube publishing stage — not yet automated

The Story Engine currently creates episode JSON and Google Flow scene prompts. It does not yet
create a video file or publish to YouTube. Add the YouTube Data API OAuth uploader only after the
Flow stage has been verified. Store OAuth client secrets/refresh tokens in GitHub Secrets, use
least-privilege scopes, add duplicate-upload/idempotency checks, and start with private or unlisted
uploads plus human review before public publishing.
