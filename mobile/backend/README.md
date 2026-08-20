# Ayloo mobile relay

The FastAPI relay keeps Groq credentials outside the Android app. It is intended only for internal
testing and does not persist uploaded audio, transcripts, or results.

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
