# Ayloo Android keyboard prototype

This is an Android Studio project for the internal Ayloo keyboard prototype.

## Run the keyboard

1. Open `mobile/android` in Android Studio (JDK 17 and an Android SDK are required).
2. Set `AYLOO_API_BASE_URL` and `AYLOO_TESTER_TOKEN` in `local.properties`. Do not commit
   either value. Android emulators reach a backend on the host at `http://10.0.2.2:8000/`.
3. Install the debug app, then open **Settings > System > Keyboard > On-screen keyboard** and
   enable Ayloo. Select Ayloo from Android's input-method picker.

The keyboard is deliberately a small English layout for the prototype. It never reads or sends
surrounding text; only audio recorded after tapping the orb is uploaded.

## Build without an Android SDK on this laptop

Push this repository to GitHub, then open **Actions > Build Android prototype APK > Run workflow**.
GitHub builds the APK in the cloud; when it completes, open the run and download the
`ayloo-keyboard-debug-apk` artifact. Before making an internal test build that can reach the
backend, add repository secrets named `AYLOO_API_BASE_URL` and `AYLOO_TESTER_TOKEN` under
**Settings > Secrets and variables > Actions**. The downloaded artifact expires after 14 days.

## Backend

See [`backend/README.md`](backend/README.md). It owns the Groq key and accepts only configured
internal-test tokens.
