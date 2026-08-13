from dataclasses import asdict, dataclass, fields
import json
import os
import shutil
import sys


APP_NAME = "Aylo"
LEGACY_APP_NAME = "VoiceFlow"


def appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def legacy_appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, LEGACY_APP_NAME)


ENV_FILE = os.path.join(appdata_dir(), "config.env")
SETTINGS_FILE = os.path.join(appdata_dir(), "config.json")
HISTORY_FILE = os.path.join(appdata_dir(), "history.json")
ERROR_LOG = os.path.join(appdata_dir(), "error.log")
CREDENTIAL_TARGET = "Aylo/GroqApiKey"
IMAGE_CREDENTIAL_TARGET = "Aylo/ImageApiKey"
OPENAI_REALTIME_CREDENTIAL_TARGET = "Aylo/OpenAIRealtimeApiKey"
GMAIL_TOKEN_TARGET = "Aylo/GmailOAuthToken"
KNOWLEDGE_DIR = os.path.join(appdata_dir(), "knowledge")
GMAIL_CLIENT_SECRET_FILE = os.path.join(appdata_dir(), "google_oauth_client.json")
LEGACY_ENV_FILE = os.path.join(legacy_appdata_dir(), "config.env")
LEGACY_SETTINGS_FILE = os.path.join(legacy_appdata_dir(), "config.json")
LEGACY_HISTORY_FILE = os.path.join(legacy_appdata_dir(), "history.json")
LEGACY_CREDENTIAL_TARGET = "VoiceFlow/GroqApiKey"
LEGACY_IMAGE_CREDENTIAL_TARGET = "VoiceFlow/ImageApiKey"
LEGACY_OPENAI_REALTIME_CREDENTIAL_TARGET = "VoiceFlow/OpenAIRealtimeApiKey"
LEGACY_GMAIL_TOKEN_TARGET = "VoiceFlow/GmailOAuthToken"


def migrate_legacy_appdata():
    """Copy user-owned VoiceFlow files into Aylo without removing the originals."""
    for legacy_path, destination_path in (
        (LEGACY_SETTINGS_FILE, SETTINGS_FILE),
        (LEGACY_HISTORY_FILE, HISTORY_FILE),
        (
            os.path.join(legacy_appdata_dir(), "google_oauth_client.json"),
            GMAIL_CLIENT_SECRET_FILE,
        ),
    ):
        _copy_legacy_file(legacy_path, destination_path)


@dataclass
class AppSettings:
    samplerate: int = 16000
    mic_device: int | str | None = None
    pre_buffer_seconds: float = 0.3
    max_record_seconds: int = 30
    min_record_seconds: float = 0.3
    silence_rms_threshold: float = 0.0008
    first_run_complete: bool = False
    mouse_side_button_mic: bool = True
    mouse_forward_action: str = "command"
    ai_features_enabled: bool = False


def load_settings(path=SETTINGS_FILE):
    if path == SETTINGS_FILE:
        migrate_legacy_appdata()
    settings = AppSettings()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                allowed = {field.name for field in fields(AppSettings)}
                values = {key: value for key, value in stored.items() if key in allowed}
                settings = AppSettings(**values)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            settings = AppSettings()
    settings = _validated_settings(settings)
    save_settings(settings, path)
    return settings


def _copy_legacy_file(legacy_path, destination_path):
    """Copy old VoiceFlow data only after the new Aylo destination is writable.

    Legacy data remains untouched so users can safely roll back if needed.
    """
    if os.path.exists(destination_path) or not os.path.isfile(legacy_path):
        return False
    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy2(legacy_path, destination_path)
        return True
    except OSError:
        return False


def save_settings(settings, path=SETTINGS_FILE):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(asdict(settings), handle, indent=2)
        handle.write("\n")


def _validated_settings(settings):
    defaults = AppSettings()
    if not isinstance(settings.samplerate, int) or settings.samplerate <= 0:
        settings.samplerate = defaults.samplerate
    if settings.mic_device is not None and not isinstance(settings.mic_device, (int, str)):
        settings.mic_device = defaults.mic_device
    if not isinstance(settings.pre_buffer_seconds, (int, float)) or settings.pre_buffer_seconds < 0:
        settings.pre_buffer_seconds = defaults.pre_buffer_seconds
    if not isinstance(settings.max_record_seconds, int) or settings.max_record_seconds <= 0:
        settings.max_record_seconds = defaults.max_record_seconds
    if not isinstance(settings.min_record_seconds, (int, float)) or settings.min_record_seconds <= 0:
        settings.min_record_seconds = defaults.min_record_seconds
    if not isinstance(settings.silence_rms_threshold, (int, float)) or settings.silence_rms_threshold < 0:
        settings.silence_rms_threshold = defaults.silence_rms_threshold
    else:
        legacy_thresholds = {
            0.001: defaults.silence_rms_threshold,
            0.002: defaults.silence_rms_threshold,
            0.005: 0.002,
            0.00005: defaults.silence_rms_threshold,
            0.000001: defaults.silence_rms_threshold,
            0.0000001: 0.0002,
        }
        settings.silence_rms_threshold = legacy_thresholds.get(
            settings.silence_rms_threshold,
            settings.silence_rms_threshold,
        )
    if not isinstance(settings.first_run_complete, bool):
        settings.first_run_complete = defaults.first_run_complete
    if not isinstance(settings.mouse_side_button_mic, bool):
        settings.mouse_side_button_mic = defaults.mouse_side_button_mic
    if settings.mouse_forward_action != "command":
        settings.mouse_forward_action = defaults.mouse_forward_action
    if not isinstance(settings.ai_features_enabled, bool):
        settings.ai_features_enabled = defaults.ai_features_enabled
    return settings


def _load_legacy_api_key(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == "GROQ_API_KEY":
                    return value.strip() or None
    return None


def _read_credential():
    return read_credential(CREDENTIAL_TARGET)


def _write_credential(key):
    write_credential(CREDENTIAL_TARGET, key)


def _migrate_credential(current_target, legacy_target):
    key = read_credential(current_target)
    if key:
        return key
    key = read_credential(legacy_target)
    if key:
        write_credential(current_target, key)
    return key


def read_credential(target_name):
    import win32cred

    try:
        credential = win32cred.CredRead(target_name, win32cred.CRED_TYPE_GENERIC)
    except Exception as exc:
        if getattr(exc, "winerror", None) == 1168:
            return None
        raise
    blob = credential["CredentialBlob"]
    value = blob.decode("utf-8") if isinstance(blob, bytes) else blob
    if isinstance(value, str) and "\x00" in value:
        value = value.replace("\x00", "")
    return value


def write_credential(target_name, value):
    import win32cred

    win32cred.CredWrite(
        {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target_name,
            "CredentialBlob": value,
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
            "UserName": APP_NAME,
        },
        0,
    )


def delete_credential(target_name):
    import win32cred

    try:
        win32cred.CredDelete(target_name, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception as exc:
        if getattr(exc, "winerror", None) != 1168:
            raise


def load_api_key(path=ENV_FILE):
    if os.environ.get("GROQ_API_KEY"):
        return os.environ["GROQ_API_KEY"]
    key = _migrate_credential(CREDENTIAL_TARGET, LEGACY_CREDENTIAL_TARGET)
    if not key:
        key = _load_legacy_api_key(path)
        if key:
            _write_credential(key)
    if not key and path == ENV_FILE:
        key = _load_legacy_api_key(LEGACY_ENV_FILE)
        if key:
            _write_credential(key)
    if key:
        os.environ["GROQ_API_KEY"] = key
    return key


def save_api_key(key, legacy_path=ENV_FILE):
    _write_credential(key)
    # VoiceFlow data is deliberately retained after migration.
    if legacy_path != LEGACY_ENV_FILE:
        try:
            os.remove(legacy_path)
        except FileNotFoundError:
            pass
    os.environ["GROQ_API_KEY"] = key


def load_image_api_key():
    if os.environ.get("POLLINATIONS_API_KEY"):
        return os.environ["POLLINATIONS_API_KEY"]
    key = _migrate_credential(IMAGE_CREDENTIAL_TARGET, LEGACY_IMAGE_CREDENTIAL_TARGET)
    if key:
        os.environ["POLLINATIONS_API_KEY"] = key
    return key


def save_image_api_key(key):
    write_credential(IMAGE_CREDENTIAL_TARGET, key)
    os.environ["POLLINATIONS_API_KEY"] = key


def load_openai_realtime_api_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    key = _migrate_credential(OPENAI_REALTIME_CREDENTIAL_TARGET, LEGACY_OPENAI_REALTIME_CREDENTIAL_TARGET)
    if key:
        os.environ["OPENAI_API_KEY"] = key
    return key


def save_openai_realtime_api_key(key):
    write_credential(OPENAI_REALTIME_CREDENTIAL_TARGET, key)
    os.environ["OPENAI_API_KEY"] = key


def model_location():
    if getattr(sys, "frozen", False):
        embedded = os.path.join(getattr(sys, "_MEIPASS", ""), "models")
        if os.path.isfile(os.path.join(embedded, "model.bin")):
            return embedded, True
        return os.path.join(os.path.dirname(sys.executable), "models"), True

    path = os.path.join(appdata_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path, False
