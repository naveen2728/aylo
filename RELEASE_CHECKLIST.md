# VoiceFlow Release Checklist

## Automated Release

Run:

```powershell
.\.venv\Scripts\python.exe release.py
```

This runs the tests, rebuilds `dist\VoiceFlow.exe`, creates a versioned portable
ZIP under `release\`, writes SHA-256 checksums, and builds an installer when Inno
Setup 6 is available.

## Optional Installer

Install Inno Setup 6, then rerun `release.py`. The installer will be written to:

```text
release\VoiceFlow-3.1.0-Setup.exe
```

## Optional Code Signing

Public distribution should use a trusted code-signing certificate. After
installing Microsoft `signtool`, set:

```powershell
$env:VOICEFLOW_SIGNTOOL = "C:\path\to\signtool.exe"
$env:VOICEFLOW_CERT_SHA1 = "YOUR_CERTIFICATE_THUMBPRINT"
```

Then rerun `release.py`. The executable and generated installer will be signed
with SHA-256 and timestamped.

## Manual Smoke Test

1. Launch `VoiceFlow.exe`.
2. Dictate with `Ctrl+Space`.
3. Run a Shift AI command.
4. Translate and summarize copied text.
5. Cancel a recording with `Backspace`.
6. Quit VoiceFlow with two quick `Escape` presses.
7. Check recent results, clear history, and launch-at-startup toggle.
