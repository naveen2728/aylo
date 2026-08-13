# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('faster_whisper')


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[('C:\\Users\\navee\\Desktop\\voice-flow\\.venv\\Lib\\site-packages\\_sounddevice_data\\portaudio-binaries\\libportaudio64bit.dll', '.'), ('C:\\Users\\navee\\Desktop\\voice-flow\\bundled_models', 'models')],
    datas=datas,
    hiddenimports=['sounddevice', 'pyperclip', 'pyautogui', 'pynput.keyboard', 'pynput.mouse', 'pynput._util.win32', 'win32gui', 'win32process', 'win32con', 'win32com.client', 'pywintypes', 'pythoncom', 'win32cred', 'win32timezone', 'psutil', 'groq', 'faster_whisper', 'ctranslate2', 'ctranslate2.specs', 'tokenizers', 'tokenizers.decoders', 'huggingface_hub', 'huggingface_hub.constants', 'googleapiclient.discovery', 'googleapiclient.errors', 'google.auth.transport.requests', 'google.oauth2.credentials', 'google_auth_oauthlib.flow', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'websocket', 'websocket._app', 'websocket._core', 'numpy', 'numpy.core._dtype_ctypes', 'numpy.random.common', 'scipy.sparse.csgraph'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Aylo',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='C:\\Users\\navee\\Desktop\\voice-flow\\version.txt',
    manifest='C:\\Users\\navee\\Desktop\\voice-flow\\aylo.manifest',
)
