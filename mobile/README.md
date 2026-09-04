# Ayloo Android keyboard prototype

This is an Android Studio project for the internal Ayloo keyboard prototype.

## Run the keyboard

1. Open `mobile/android` in Android Studio (JDK 17 and an Android SDK are required).
2. Set `AYLOO_API_BASE_URL` and `AYLOO_TESTER_TOKEN` in `local.properties`. Do not commit
   either value. Android emulators reach a backend on the host at `http://10.0.2.2:8000/`.
3. Install the debug app, then open **Settings > System > Keyboard > On-screen keyboard** and
   enable Ayloo. Select Ayloo from Android's input-method picker.

The internal beta uses a familiar English QWERTY layout with automatic capitalization, two symbol
pages, context-aware Enter keys, field-specific number/phone layouts, Unicode-aware hold backspace,
adaptive light/dark colors, slide-correcting multi-touch keys, safe local spelling/next-word
suggestions, a session clipboard, expanded emoji categories, and a compact Dictate/AI toggle beside
an icon-only microphone. Suggestions inspect at most 96 characters immediately before
the cursor in memory; typed context is never uploaded or stored. Only audio recorded after tapping
the microphone is uploaded. Voice, suggestions, clipboard content, and retry actions are hidden in
password fields. Tap comma normally for punctuation, or hold it briefly to open emoji.

## Build without an Android SDK on this laptop

Push this repository to GitHub, then open **Actions > Build Android prototype APK > Run workflow**.
GitHub builds the APK in the cloud; when it completes, open the run and download the
`ayloo-keyboard-0.6.0-beta-apk` artifact. Before making an internal test build that can reach the
backend, add repository secrets named `AYLOO_API_BASE_URL` and `AYLOO_TESTER_TOKEN` under
**Settings > Secrets and variables > Actions**. The downloaded artifact expires after 90 days.
The cloud build is installed as **Ayloo Keyboard Beta** (`com.ayloo.keyboard.internal`), beside any
older prototype. Earlier workflows accidentally produced a new disposable certificate on every
run, so they cannot be upgraded safely. Version 0.6 explicitly uses the restored internal signing
key; the workflow refuses to publish if that key is missing or if the finished APK does not match
it. Future beta versions can therefore update version 0.6 normally.

## Backend

See [`backend/README.md`](backend/README.md). It owns the Groq key and accepts only configured
internal-test tokens.
