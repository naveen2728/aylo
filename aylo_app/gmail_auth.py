import json
import os

from .config import (
    GMAIL_CLIENT_SECRET_FILE,
    GMAIL_TOKEN_TARGET,
    LEGACY_GMAIL_TOKEN_TARGET,
    _migrate_credential,
    delete_credential,
    read_credential,
    write_credential,
)


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailAuthError(RuntimeError):
    pass


def load_token():
    value = _migrate_credential(GMAIL_TOKEN_TARGET, LEGACY_GMAIL_TOKEN_TARGET)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def save_token(token_data):
    write_credential(GMAIL_TOKEN_TARGET, json.dumps(token_data))


def delete_token():
    delete_credential(GMAIL_TOKEN_TARGET)


def is_connected():
    return _has_required_scopes(load_token())


def get_credentials(client_secret_file=GMAIL_CLIENT_SECRET_FILE, run_flow=True):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise GmailAuthError("Install Google auth packages from requirements.txt, then restart Aylo.") from exc

    token_data = load_token()
    credentials = Credentials.from_authorized_user_info(token_data, SCOPES) if token_data else None
    has_scopes = _has_required_scopes(token_data)

    if credentials and has_scopes and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        save_token(json.loads(credentials.to_json()))
        return credentials
    if credentials and has_scopes and credentials.valid:
        return credentials

    if not run_flow:
        raise GmailAuthError("Gmail needs to be reconnected to allow draft creation.")
    if not os.path.exists(client_secret_file):
        raise GmailAuthError(
            "Missing Google OAuth client file. Save it as google_oauth_client.json in %APPDATA%\\Aylo."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    credentials = flow.run_local_server(port=0)
    save_token(json.loads(credentials.to_json()))
    return credentials


def _has_required_scopes(token_data):
    if not token_data:
        return False
    saved_scopes = token_data.get("scopes") or token_data.get("scope") or []
    if isinstance(saved_scopes, str):
        saved_scopes = saved_scopes.split()
    return set(SCOPES).issubset(set(saved_scopes))
