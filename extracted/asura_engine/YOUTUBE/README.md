# YouTube publishing — not implemented

The current workflow does not upload videos to YouTube. A future uploader needs a Google Cloud project, YouTube Data API configuration, OAuth consent and refresh-token handling. Keep credentials in GitHub Secrets and never commit them. Upload only after a rendered video exists and the user has approved the title, description, visibility and destination channel.
