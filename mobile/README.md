# Ayloo Android keyboard prototype

This is an Android Studio project for the internal Ayloo keyboard prototype.

## Run the keyboard

1. Open `mobile/android` in Android Studio (JDK 17 and an Android SDK are required).
2. Set `AYLOO_API_BASE_URL` and `AYLOO_TESTER_TOKEN` in `local.properties`. Do not commit
   either value. Android emulators reach a backend on the host at `http://10.0.2.2:8000/`.
3. Install the debug app, then open **Settings > System > Keyboard > On-screen keyboard** and
   enable Ayloo. Select Ayloo from Android's input-method picker.

The internal beta uses a familiar English QWERTY layout with automatic capitalization, two symbol
pages, context-aware Enter keys, number/phone layouts, tap-and-hold backspace, light/dark colors,
a multi-touch key surface, local next-word suggestions, a session clipboard, emoji categories,
and a compact Dictate/AI voice toggle. Suggestions inspect at most 96 characters immediately before
the cursor in memory; typed context is never uploaded or stored. Only audio recorded after tapping
the orb is uploaded. Voice capture and suggestions are disabled in password fields.

## Build without an Android SDK on this laptop

Push this repository to GitHub, then open **Actions > Build Android prototype APK > Run workflow**.
GitHub builds the APK in the cloud; when it completes, open the run and download the
`ayloo-keyboard-0.5.0-beta-apk` artifact. Before making an internal test build that can reach the
backend, add repository secrets named `AYLOO_API_BASE_URL` and `AYLOO_TESTER_TOKEN` under
**Settings > Secrets and variables > Actions**. The downloaded artifact expires after 14 days.
The workflow caches its internal debug signing key so later beta builds can update this build.
Because older workflow runs used disposable signing keys, upgrading from a pre-0.4 APK may require
one final uninstall/reinstall; builds from 0.4 onward should update normally while that cache exists.

## Backend

See [`backend/README.md`](backend/README.md). It owns the Groq key and accepts only configured
internal-test tokens.
