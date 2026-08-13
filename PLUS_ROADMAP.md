# Aylo Plus Roadmap

This project is a modular Windows desktop app built with Tkinter, faster-whisper,
Groq, and PyInstaller. The Plus upgrade should happen in stages so each version
remains runnable.

## Stage 1 - Build Foundation

- Add a real dependency manifest.
- Keep one official app entry point: `main.py`.
- Keep one official build command: `python build.py`.
- Remove hardcoded local paths from packaging where possible.
- Verify the app runs from source before rebuilding the executable.

## Stage 2 - App Reliability

- Make API-key setup optional so basic dictation works without Groq.
- Add clearer error messages for microphone, model, and API failures. In progress: microphone and recording errors improved.
- Store settings in a structured config file. Done: `%APPDATA%\Aylo\config.json`.
- Add startup checks for Python, dependencies, bundled model files, and DLLs.

## Stage 3 - Plus Features

- Settings window for API key, model, microphone, hotkeys, and startup behavior. In progress: microphone, sensitivity, and recording duration are configurable.
- Dictation modes: raw, clean, email, chat, prompt, code.
- Command history with quick re-copy. Done: the orb menu stores the latest 20 results.
- Better command mode for selected text and clipboard edits.
- Clipboard rewrite menu with presets and custom note instructions. Done.
- Friendly Groq error messages and Markdown fence cleanup for generated output. Done.
- Answer-only AI cleanup removes occasional acknowledgements and paste-unfriendly filler. Done.
- Automatic pastes restore the user's previous clipboard content. Done.
- Larger polished orb UI with readable menus and contained waveform animation. Done.
- Optional launch at Windows startup. Done.
- Clear recent history from the orb menu. Done.
- Store the Groq API key in Windows Credential Manager and migrate legacy plain-text keys. Done.
- Require two quick Escape presses to quit while keeping Backspace recording cancellation. Done.

## Stage 4 - Packaging

- Rebuild the app with bundled Whisper model files.
- Add a versioned release folder. Done.
- Add an installer definition and release automation. Done.
- Sign public releases with a trusted certificate. External certificate required.

## Current Build Command

```powershell
cd path\to\voice-flow
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
python build.py
```
