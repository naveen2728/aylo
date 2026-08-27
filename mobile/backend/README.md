# Ayloo mobile relay

The FastAPI relay keeps Groq credentials outside the Android app. It is intended only for internal
testing and does not persist uploaded audio, transcripts, or results.

## Internal API

- `POST /v1/commands` accepts a private audio upload plus `duration_ms` and `mode` (`dictate` or `command`).
- `POST /v1/text-actions` accepts selected `text` and one allowlisted transformation `action`.
- `GET /health` exposes deployment health only.

Both POST routes require the internal bearer token, share the per-tester rate limit, and reject
oversized input. Logs contain request metadata only, never audio, selected text, transcripts, or
generated results.

## Render deployment

The repository's `render.yaml` defines a Free Python Web Service rooted at this directory. In
Render, create a **Blueprint** from the `codex/aylo-repository-link` branch, select the Free plan,
and enter `GROQ_API_KEY` and `AYLOO_TESTER_TOKENS` directly in Render's Environment section. Never
put either value in this repository, the Android project, or GitHub Actions logs. Render assigns an
HTTPS `https://…onrender.com` URL; use that exact URL as `AYLOO_API_BASE_URL` in GitHub Actions.

The health check is `GET /health`; the service starts with
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Free services sleep after inactivity, so the
Android app waits up to 150 seconds for the first request and gives the user a retry message.

```powershell
cd mobile/backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:GROQ_API_KEY = "..."
$env:AYLOO_TESTER_TOKENS = "a-long-random-test-token"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use HTTPS outside the Android emulator. Configure a unique high-entropy tester token per tester,
remove it when testing ends, and place the service behind an HTTPS reverse proxy.
