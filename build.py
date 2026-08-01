"""
build.py - Builds VoiceFlow.exe
Run with: python build.py

What this does:
1. Downloads the Whisper model so it's bundled into the .exe (no internet needed at runtime)
2. Finds portaudio.dll and pywin32 DLLs automatically
3. Runs PyInstaller with all required flags
4. Creates dist/VoiceFlow.exe
"""

import os
import sys
import glob
import subprocess
import importlib.util

VERSION = "3.1.0"

# =========================
# PATHS
# =========================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR  = os.path.join(SCRIPT_DIR, "bundled_models")
os.makedirs(MODEL_DIR, exist_ok=True)

REQUIRED_MODULES = [
    "faster_whisper",
    "sounddevice",
    "numpy",
    "groq",
    "pyperclip",
    "pyautogui",
    "pynput",
    "win32gui",
    "win32process",
    "psutil",
    "PyInstaller",
]

# =========================
# PRE-FLIGHT CHECKS
# =========================

print("=" * 50)
print("VoiceFlow Plus build pre-flight")
print("=" * 50)

if sys.version_info < (3, 11) or sys.version_info >= (3, 13):
    print("ERROR: Use Python 3.11 or 3.12 for this build.")
    print(f"Current Python: {sys.version.split()[0]}")
    sys.exit(1)

missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
if missing:
    print("ERROR: Missing required Python packages:")
    for name in missing:
        print(f"  - {name}")
    print("\nInstall dependencies first:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

print(f"Python: {sys.version.split()[0]}")
print("Dependencies: OK\n")

# =========================
# STEP 1 - Download Whisper model for offline bundling
# =========================

print("=" * 50)
print("Step 1: Downloading Whisper model for offline bundling...")
print("(This only happens once. ~150MB)")
print("=" * 50)

try:
    from faster_whisper import download_model
    model_path = download_model("base.en", output_dir=MODEL_DIR)
    print(f"Model saved to: {model_path}\n")
except Exception as e:
    print(f"ERROR downloading model: {e}")
    print("Check your internet connection and try again.")
    sys.exit(1)

# =========================
# STEP 2 - Find portaudio.dll
# =========================

print("Step 2: Locating portaudio.dll...")
def find_portaudio():
    try:
        import site
        for sp in site.getsitepackages():
            pattern = os.path.join(sp, "_sounddevice_data", "portaudio-binaries", "*.dll")
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
    except Exception:
        pass
    # Fallback: walk entire venv
    python_dir = os.path.dirname(sys.executable)
    for root, dirs, files in os.walk(python_dir):
        for f in files:
            if "portaudio" in f.lower() and f.lower().endswith(".dll"):
                return os.path.join(root, f)
    return None
portaudio = find_portaudio()
if not portaudio:
    print("ERROR: Could not find portaudio.dll")
    print("Try: pip install sounddevice --force-reinstall")
    sys.exit(1)
print(f"Found: {portaudio}\n")

# =========================
# STEP 3 - Find pywin32 DLLs
# =========================

print("Step 3: Locating pywin32 DLLs...")

def find_pywin32_dlls():
    python_dir = os.path.dirname(sys.executable)
    found = []
    for root, dirs, files in os.walk(python_dir):
        for f in files:
            if (f.lower().startswith("pywintypes") or f.lower().startswith("pythoncom")) \
               and f.lower().endswith(".dll"):
                found.append(os.path.join(root, f))
    return found

pywin32_dlls = find_pywin32_dlls()
if not pywin32_dlls:
    print("WARNING: Could not find pywin32 DLLs - window detection may fail in the .exe")
else:
    for d in pywin32_dlls:
        print(f"Found: {d}")
print()

# =========================
# STEP 4 - Create version info file (reduces SmartScreen warnings)
# =========================

print("Step 4: Creating version info...")

version_txt = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(3, 1, 0, 0),
    prodvers=(3, 1, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'VoiceFlow'),
         StringStruct(u'FileDescription', u'VoiceFlow - AI Voice to Text'),
         StringStruct(u'FileVersion', u'{VERSION}'),
         StringStruct(u'InternalName', u'VoiceFlow'),
         StringStruct(u'LegalCopyright', u'VoiceFlow'),
         StringStruct(u'OriginalFilename', u'VoiceFlow.exe'),
         StringStruct(u'ProductName', u'VoiceFlow'),
         StringStruct(u'ProductVersion', u'{VERSION}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)"""

version_file = os.path.join(SCRIPT_DIR, "version.txt")
with open(version_file, "w") as f:
    f.write(version_txt)
print(f"Version file: {version_file}\n")

manifest_file = os.path.join(SCRIPT_DIR, "voiceflow.manifest")
if not os.path.exists(manifest_file):
    print(f"ERROR: Missing Windows DPI manifest: {manifest_file}")
    sys.exit(1)

# =========================
# STEP 5 - Build PyInstaller command
# =========================

print("Step 5: Building .exe with PyInstaller...")
print("(This takes 2-5 minutes)\n")

add_binaries = [
    f"{portaudio};.",
]
for dll in pywin32_dlls:
    add_binaries.append(f"{dll};.")

# Bundle the downloaded model
add_binaries.append(f"{MODEL_DIR};models")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",               # no console window shown to end users
    "--name", "VoiceFlow",
    "--version-file", version_file,
    "--manifest", manifest_file,
    "--clean",                  # clean PyInstaller cache before building
    "--collect-data", "faster_whisper",
]

# Add all binaries
for b in add_binaries:
    cmd += ["--add-binary", b]

# Hidden imports - everything PyInstaller commonly misses
hidden = [
    "sounddevice",
    "pyperclip",
    "pyautogui",
    "pynput.keyboard",
    "pynput.mouse",
    "pynput._util.win32",
    "win32gui",
    "win32process",
    "win32con",
    "win32com.client",
    "pywintypes",
    "pythoncom",
    "win32cred",
    "win32timezone",
    "psutil",
    "groq",
    "faster_whisper",
    "ctranslate2",
    "ctranslate2.specs",
    "tokenizers",
    "tokenizers.decoders",
    "huggingface_hub",
    "huggingface_hub.constants",
    "googleapiclient.discovery",
    "googleapiclient.errors",
    "google.auth.transport.requests",
    "google.oauth2.credentials",
    "google_auth_oauthlib.flow",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    "websocket",
    "websocket._app",
    "websocket._core",
    "numpy",
    "numpy.core._dtype_ctypes",
    "numpy.random.common",
    "scipy.sparse.csgraph",
]

for h in hidden:
    cmd += ["--hidden-import", h]

cmd.append("main.py")

result = subprocess.run(cmd, cwd=SCRIPT_DIR)

# =========================
# RESULT
# =========================

print("\n" + "=" * 50)
if result.returncode == 0:
    exe_path = os.path.join(SCRIPT_DIR, "dist", "VoiceFlow.exe")
    print("BUILD COMPLETE!")
    print(f"\nYour .exe is at:\n  {exe_path}")
    print("\nWhat to tell users:")
    print("  - Double-click VoiceFlow.exe to start")
    print("  - First launch asks for a free Groq API key")
    print("  - Hold Right Shift to record dictation, release to paste")
    print("  - Optional: enable mouse side buttons in Settings")
    print("    Back records dictation; Forward records an AI command")
    print("    VoiceFlow blocks the native browser Back/Forward mouse action")
    print("  - Hold Ctrl+Space for AI commands")
    print("  - Right-click the orb for Settings, Diagnostics, Setup, Reconnect AI, or Quit")
    print("  - Hotkeys don't work when an Admin app is focused")
    print("\nWindows SmartScreen warning:")
    print("  Users will see 'Unknown publisher' - click 'More info' -> 'Run anyway'")
    print("  This goes away after enough users run it (or with a code signing cert)")
else:
    print("BUILD FAILED.")
    print("Check the output above. Common fixes:")
    print("  pip install pyinstaller --upgrade")
    print("  pip install pywin32 --upgrade")
    sys.exit(1)
