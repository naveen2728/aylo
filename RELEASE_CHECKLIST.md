# Aylo Release Checklist

## Automated Release

Run:

```powershell
.\.venv\Scripts\python.exe release.py
```

This runs the tests, rebuilds `dist\Aylo.exe`, creates a versioned portable
ZIP under `release\`, writes SHA-256 checksums, and builds an installer when Inno
Setup 6 is available.

## Optional Installer

Install Inno Setup 6, then rerun `release.py`. The installer will be written to:

```text
release\Aylo-3.1.1-Setup.exe
```

## Optional Code Signing

Public distribution should use a trusted code-signing certificate. After
installing Microsoft `signtool`, set:

```powershell
$env:AYLO_SIGNTOOL = "C:\path\to\signtool.exe"
$env:AYLO_CERT_SHA1 = "YOUR_CERTIFICATE_THUMBPRINT"
```

Then rerun `release.py`. The executable and generated installer will be signed
with SHA-256 and timestamped.

## Manual Smoke Test

1. Launch `Aylo.exe`.
2. Dictate with `Ctrl+Space`.
3. Run a Shift AI command.
4. Translate and summarize copied text.
5. Cancel a recording with `Backspace`.
6. Quit Aylo with two quick `Escape` presses.
7. Check recent results, clear history, and launch-at-startup toggle.
