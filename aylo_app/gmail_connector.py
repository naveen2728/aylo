import base64
from email.message import EmailMessage
import email.utils

from .gmail_auth import GmailAuthError, delete_token, get_credentials, is_connected
from .gmail_index import GmailIndex, normalize_gmail_message


class GmailSyncError(RuntimeError):
    pass


DEEP_SYNC_QUERIES = [
    ("important", "is:important newer_than:365d", 80),
    ("starred", "is:starred newer_than:365d", 80),
    ("unread", "is:unread newer_than:90d", 80),
    ("primary", "category:primary newer_than:45d", 80),
    ("recent", "newer_than:30d in:anywhere", 80),
]


def connect_gmail():
    get_credentials(run_flow=True)


def disconnect_gmail():
    delete_token()


def gmail_status(index=None):
    index = index or GmailIndex()
    state = "connected" if is_connected() else "not connected"
    count = index.count_messages()
    latest = index.latest_sync()
    if latest:
        return f"Gmail {state}. {count} messages indexed. Last sync: {latest}."
    return f"Gmail {state}. {count} messages indexed."


def sync_recent_gmail(limit=50, query="newer_than:30d in:anywhere", index=None):
    try:
        credentials = get_credentials(run_flow=False)
        service = _build_service(credentials)
        refs = _list_message_refs(service, query, limit)
        messages = _fetch_messages(service, refs)
        index = index or GmailIndex()
        index.upsert_messages(messages)
        return len(messages)
    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailSyncError(f"Gmail sync failed: {exc}") from exc


def sync_gmail_knowledge(index=None, queries=None):
    try:
        credentials = get_credentials(run_flow=False)
        service = _build_service(credentials)
        queries = queries or DEEP_SYNC_QUERIES
        index = index or GmailIndex()
        seen_ids = set()
        total = 0
        for _, query, limit in queries:
            refs = []
            for ref in _list_message_refs(service, query, limit):
                message_id = ref.get("id")
                if message_id and message_id not in seen_ids:
                    seen_ids.add(message_id)
                    refs.append(ref)
            messages = _fetch_messages(service, refs)
            if messages:
                index.upsert_messages(messages)
                total += len(messages)
        return total
    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailSyncError(f"Gmail deep sync failed: {exc}") from exc


def create_gmail_draft(to, subject, body, thread_id=None):
    try:
        credentials = get_credentials(run_flow=False)
        service = _build_service(credentials)
        draft_message = _build_message_payload(to, subject, body, thread_id)
        draft = service.users().drafts().create(userId="me", body={"message": draft_message}).execute()
        return draft.get("id", "")
    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailSyncError(f"Gmail draft creation failed: {exc}") from exc


def send_gmail_message(to, subject, body, thread_id=None):
    try:
        credentials = get_credentials(run_flow=False)
        service = _build_service(credentials)
        sent = service.users().messages().send(
            userId="me",
            body=_build_message_payload(to, subject, body, thread_id),
        ).execute()
        return sent.get("id", "")
    except GmailAuthError:
        raise
    except Exception as exc:
        raise GmailSyncError(f"Gmail send failed: {exc}") from exc


def sender_email(sender):
    _, address = email.utils.parseaddr(sender or "")
    return address or sender


def _build_service(credentials):
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailSyncError("Install Google API packages from requirements.txt, then restart Aylo.") from exc
    return build("gmail", "v1", credentials=credentials)


def _list_message_refs(service, query, limit):
    refs = []
    page_token = None
    while len(refs) < limit:
        batch_size = min(100, limit - len(refs))
        request = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=batch_size,
            pageToken=page_token,
        )
        listing = request.execute()
        refs.extend(listing.get("messages", []) or [])
        page_token = listing.get("nextPageToken")
        if not page_token:
            break
    return refs[:limit]


def _fetch_messages(service, refs):
    messages = []
    for ref in refs:
        raw = service.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        message = normalize_gmail_message(raw)
        if message.message_id:
            messages.append(message)
    return messages


def _reply_subject(subject):
    subject = (subject or "").strip() or "(no subject)"
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def _build_message_payload(to, subject, body, thread_id=None):
    message = EmailMessage()
    message["To"] = to
    message["Subject"] = _reply_subject(subject)
    message.set_content(body)
    payload = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")}
    if thread_id:
        payload["threadId"] = thread_id
    return payload
