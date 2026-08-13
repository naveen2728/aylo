# Contributing

Thank you for helping improve Aylo Desktop.

## Before you start

For a substantial feature or behavior change, open an issue describing the problem and proposed direction first. Small bug fixes, tests, and documentation improvements can go directly to a pull request.

By contributing, you agree that your contribution is licensed under the Apache License 2.0.

## Development setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Run the application with:

```powershell
python main.py
```

Run the test suite with:

```powershell
python -m unittest discover -s tests -v
```

## Pull requests

- Keep changes focused and explain the user-visible outcome.
- Add or update tests for changed behavior.
- Do not commit API keys, OAuth files, email data, audio recordings, logs, models, generated executables, or build output.
- Preserve the local-first behavior of basic transcription.
- Make cloud-provider behavior explicit in the UI and documentation.
- Avoid logging credentials, raw audio, Gmail bodies, or other sensitive content.
- Update privacy and third-party notices when adding a service or dependency.

## Provider integrations

New AI providers should be isolated behind a small provider interface, use user-supplied credentials, expose clear failure messages, and be testable without live network calls. Unit tests must mock provider connections and must never consume paid API credits.

## Reporting security issues

Do not publish vulnerabilities or leaked credentials in a public issue. Follow [SECURITY.md](SECURITY.md).
