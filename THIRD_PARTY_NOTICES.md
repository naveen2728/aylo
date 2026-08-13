# Third-Party Notices

Aylo Desktop depends on third-party software that is not relicensed under this project's Apache License 2.0. Each dependency remains subject to its own license and notices.

Direct Python dependencies are listed in `requirements.txt`. They include software under Apache-2.0, MIT-family, BSD-family, PSF, LGPL, and other compatible or exception-based terms. Transitive dependencies may add further notices.

Important bundled or build-time components include:

- `faster-whisper` — MIT
- `Systran/faster-whisper-base.en` model files downloaded by the current build — MIT
- CTranslate2 — MIT
- PortAudio, distributed through `python-sounddevice` builds — MIT-style license
- PyInstaller — GPL with the PyInstaller bootloader exception
- `pynput` — LGPLv3
- NumPy and SciPy binary distributions — BSD-family licenses plus notices for bundled numerical libraries

Cloud APIs and SDKs also have separate service terms. An open-source license for this application does not grant free API usage or change the terms of Groq, OpenAI, Pollinations, Google, Gmail, or any other provider.

Before publishing a binary release, generate a license report from the exact locked build environment and ship the applicable license texts and notices alongside the binary. Dependency versions are currently unpinned, so this file is a review aid rather than a complete binary-distribution notice bundle.
