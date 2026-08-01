"""Create versioned VoiceFlow release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


VERSION = "3.1.1"
ROOT = Path(__file__).resolve().parent
DIST_EXE = ROOT / "dist" / "VoiceFlow.exe"
RELEASE_ROOT = ROOT / "release"
PORTABLE_DIR = RELEASE_ROOT / f"VoiceFlow-{VERSION}"
PORTABLE_EXE = PORTABLE_DIR / "VoiceFlow.exe"
STANDALONE_EXE = RELEASE_ROOT / f"VoiceFlow-{VERSION}.exe"
PORTABLE_ZIP = RELEASE_ROOT / f"VoiceFlow-{VERSION}-portable.zip"
CHECKSUMS_FILE = RELEASE_ROOT / f"VoiceFlow-{VERSION}-SHA256SUMS.txt"
INNO_SCRIPT = ROOT / "installer" / "VoiceFlow.iss"
FRIEND_GUIDE = ROOT / "FRIEND_TESTING.md"
PORTABLE_GUIDE = PORTABLE_DIR / "VoiceFlow Quick Start.txt"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def run(command):
    print(f"> {' '.join(str(part) for part in command)}")
    subprocess.run(command, cwd=ROOT, check=True)


def find_inno_setup():
    configured = os.environ.get("VOICEFLOW_ISCC")
    candidates = [
        configured,
        shutil.which("iscc"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def sign(path):
    signtool = os.environ.get("VOICEFLOW_SIGNTOOL")
    certificate_sha1 = os.environ.get("VOICEFLOW_CERT_SHA1")
    if not signtool or not certificate_sha1:
        return False
    run(
        [
            signtool,
            "sign",
            "/sha1",
            certificate_sha1,
            "/fd",
            "SHA256",
            "/tr",
            "http://timestamp.digicert.com",
            "/td",
            "SHA256",
            str(path),
        ]
    )
    return True


def create_portable_release():
    RELEASE_ROOT.mkdir(exist_ok=True)
    PORTABLE_DIR.mkdir(exist_ok=True)
    shutil.copy2(DIST_EXE, PORTABLE_EXE)
    shutil.copy2(DIST_EXE, STANDALONE_EXE)
    shutil.copy2(FRIEND_GUIDE, PORTABLE_GUIDE)
    with zipfile.ZipFile(PORTABLE_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(PORTABLE_EXE, arcname="VoiceFlow.exe")
        archive.write(PORTABLE_GUIDE, arcname="VoiceFlow Quick Start.txt")
    return [STANDALONE_EXE, PORTABLE_ZIP]


def build_installer():
    iscc = find_inno_setup()
    if not iscc:
        print("Installer skipped: install Inno Setup 6 or set VOICEFLOW_ISCC.")
        return None
    run([iscc, f"/DMyAppVersion={VERSION}", str(INNO_SCRIPT)])
    installer = RELEASE_ROOT / f"VoiceFlow-{VERSION}-Setup.exe"
    sign(installer)
    return installer


def write_checksums(paths):
    with open(CHECKSUMS_FILE, "w", encoding="ascii") as handle:
        for path in paths:
            handle.write(f"{sha256(path)}  {path.name}\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true", help="Package the existing dist executable.")
    args = parser.parse_args()

    if not args.skip_build:
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])
        run([sys.executable, "build.py"])
    if not DIST_EXE.is_file():
        raise SystemExit("dist\\VoiceFlow.exe is missing. Run python build.py first.")

    signed = sign(DIST_EXE)
    artifacts = create_portable_release()
    installer = build_installer()
    if installer:
        artifacts.append(installer)
    write_checksums(artifacts)

    print(f"\nRelease ready: {RELEASE_ROOT}")
    print(f"Portable ZIP: {PORTABLE_ZIP.name}")
    print("Code signing: complete" if signed else "Code signing: skipped (certificate tools not configured)")


if __name__ == "__main__":
    main()
