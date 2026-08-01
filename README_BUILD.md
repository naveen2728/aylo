# VoiceFlow - Building and Distributing the EXE

## Quick Start

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python build.py
```

You can also double-click `build.bat`. It calls the same Python build script.

For a shareable release ZIP and optional installer, run:

```powershell
python release.py
```

## Requirements

- Windows 10 or 11, 64-bit
- Python 3.11 or 3.12, 64-bit
- Runtime and build dependencies from `requirements.txt`

## What The Build Does

`build.py`:

1. Checks Python and required packages.
2. Downloads the Whisper `base.en` model into `bundled_models/` if needed.
3. Finds PortAudio and pywin32 DLLs.
4. Runs PyInstaller in one-file, windowed mode.
5. Produces `dist\VoiceFlow.exe`.

The model is bundled inside the EXE. VoiceFlow can therefore run local transcription
without downloading the model on the user's machine.

## What Happens On First Run

1. VoiceFlow asks for an optional Groq API key.
2. The app loads the bundled local speech model.
3. The floating orb appears after the microphone opens.

Without a Groq API key, basic local dictation still works. AI cleanup and voice
commands require internet access and a Groq API key.

The API key is stored securely in Windows Credential Manager under:

```text
VoiceFlow/GroqApiKey
```

Older `%APPDATA%\VoiceFlow\config.env` files are migrated automatically and removed.

Audio and device settings are stored at:

```text
%APPDATA%\VoiceFlow\config.json
```

Recording errors are logged at:

```text
%APPDATA%\VoiceFlow\error.log
```

The latest 20 successful dictation and AI results are stored at:

```text
%APPDATA%\VoiceFlow\history.json
```

## Controls

- Hold `Right Shift` to dictate. Release to paste the transcription.
- Hold `Ctrl+Space` to record an AI command. Release to run it.
- Optional: enable mouse side buttons from Settings. Back side button records dictation; Forward side button records an AI command.
- Press `Backspace` while recording to cancel and discard the recording.
- Press `Escape` twice quickly to quit VoiceFlow. A single Escape press is ignored.
- Right-click the orb to rewrite copied text, recopy or clear recent results, launch VoiceFlow with Windows, change microphone settings, open Diagnostics, rerun Setup, reconnect AI, update the API key, open the log, or quit.
- Hotkeys may not work while an Administrator app is focused.

Clipboard-based AI commands and rewrites accept up to 100 copied lines at a time.
Generated code has outer Markdown fences removed before it is copied or pasted.
Automatic dictation and AI-command pastes restore the text that was previously
on the clipboard. Right-click rewrite actions intentionally leave their result copied.

The `Start VoiceFlow with Windows` menu option stores a current-user startup entry.
It does not require Administrator access.

## Distribution

Use the portable ZIP under `release\`. Python is not required on the target machine.
When Inno Setup 6 is installed, `release.py` also generates a Windows installer.

PyInstaller executables may trigger antivirus false positives or Windows SmartScreen.
Code signing is the long-term solution for public distribution. See
`RELEASE_CHECKLIST.md` for the optional signing configuration.

## Project Layout

```text
main.py               # Small executable entry point
build.py              # Official build command
voiceflow_app/        # Application modules
bundled_models/       # Whisper files included during the build
build/                # PyInstaller temporary output
dist/                 # Release executable
release/              # Versioned portable ZIP and optional installer
installer/            # Inno Setup installer definition
tests/                # Lightweight unit tests
```
