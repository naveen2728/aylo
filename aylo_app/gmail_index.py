from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import email.utils
import html
import os
import re
import sqlite3

from .config import KNOWLEDGE_DIR


IMPORTANT_TERMS = {
    "approval", "approve", "blocked", "client", "deadline", "due", "invoice",
    "issue", "meeting", "payment", "proposal", "security", "urgent",
}


@dataclass
class GmailMessage:
    message_id: str
    thread_id: str
    sender: str
    recipients: str
    subject: str
    date: str
    snippet: str
    body: str
    labels: tuple[str, ...]
    unread: bool
    starred: bool
    important: bool


def default_index_path():
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    return os.path.join(KNOWLEDGE_DIR, "gmail.sqlite3")


class GmailIndex:
    def __init__(self, path=None):
        self.path = path or default_index_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.path)

    def _init_db(self):
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gmail_messages (
                    message_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    sender TEXT,
                    recipients TEXT,
                    subject TEXT,
                    message_date TEXT,
                    snippet TEXT,
                    body TEXT,
                    labels TEXT,
                    unread INTEGER,
                    starred INTEGER,
                    important INTEGER,
                    synced_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_gmail_message_date ON gmail_messages(message_date)")
            conn.commit()
        finally:
            conn.close()

    def upsert_messages(self, messages):
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            for message in messages:
                conn.execute(
                    """
                    INSERT INTO gmail_messages (
                        message_id, thread_id, sender, recipients, subject, message_date,
                        snippet, body, labels, unread, starred, important, synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        thread_id=excluded.thread_id,
                        sender=excluded.sender,
                        recipients=excluded.recipients,
                        subject=excluded.subject,
                        message_date=excluded.message_date,
                        snippet=excluded.snippet,
                        body=excluded.body,
                        labels=excluded.labels,
                        unread=excluded.unread,
                        starred=excluded.starred,
                        important=excluded.important,
                        synced_at=excluded.synced_at
                    """,
                    (
                        message.message_id,
                        message.thread_id,
                        message.sender,
                        message.recipients,
                        message.subject,
                        message.date,
                        message.snippet,
                        message.body,
                        ",".join(message.labels),
                        int(message.unread),
                        int(message.starred),
                        int(message.important),
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def count_messages(self):
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM gmail_messages").fetchone()[0]
        finally:
            conn.close()

    def latest_sync(self):
        conn = self._connect()
        try:
            row = conn.execute("SELECT MAX(synced_at) FROM gmail_messages").fetchone()
        finally:
            conn.close()
        return row[0] if row and row[0] else None

    def search(self, query, limit=8):
        terms = _query_terms(query)
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT message_id, sender, subject, message_date, snippet, body, labels, unread, starred, important
                FROM gmail_messages
                ORDER BY message_date DESC
                LIMIT 200
                """
            ).fetchall()
        finally:
            conn.close()
        ranked = []
        for row in rows:
            score, reasons = score_message(row, terms)
            if score > 0:
                ranked.append((score, reasons, row))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [_row_to_result(row, score, reasons) for score, reasons, row in ranked[:limit]]

    def get_message(self, message_id):
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT message_id, thread_id, sender, recipients, subject, message_date,
                       snippet, body, labels, unread, starred, important
                FROM gmail_messages
                WHERE message_id = ?
                """,
                (message_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        labels = tuple(label for label in (row[8] or "").split(",") if label)
        return GmailMessage(
            message_id=row[0],
            thread_id=row[1],
            sender=row[2],
            recipients=row[3],
            subject=row[4],
            date=row[5],
            snippet=row[6],
            body=row[7],
            labels=labels,
            unread=bool(row[9]),
            starred=bool(row[10]),
            important=bool(row[11]),
        )


def normalize_gmail_message(raw_message):
    payload = raw_message.get("payload", {})
    headers = {item.get("name", "").lower(): item.get("value", "") for item in payload.get("headers", [])}
    labels = tuple(raw_message.get("labelIds", []) or [])
    return GmailMessage(
        message_id=raw_message.get("id", ""),
        thread_id=raw_message.get("threadId", ""),
        sender=headers.get("from", ""),
        recipients=headers.get("to", ""),
        subject=headers.get("subject", "(no subject)"),
        date=_normalize_date(headers.get("date", "")),
        snippet=_clean_display_text(raw_message.get("snippet", "")),
        body=_extract_body(payload),
        labels=labels,
        unread="UNREAD" in labels,
        starred="STARRED" in labels,
        important="IMPORTANT" in labels,
    )


def score_message(row, query_terms):
    _, sender, subject, message_date, snippet, body, labels, unread, starred, important = row
    searchable = f"{sender} {subject} {snippet} {body}".lower()
    label_text = labels or ""
    score = 0
    reasons = []
    if unread:
        score += 2
        reasons.append("unread")
    if starred:
        score += 8
        reasons.append("starred")
    if important or "IMPORTANT" in label_text:
        score += 8
        reasons.append("marked important")
    matched_terms = [term for term in query_terms if term in searchable]
    if matched_terms:
        score += min(8, len(matched_terms) * 2)
        reasons.append("matches your question")
    matched_important = sorted(term for term in IMPORTANT_TERMS if term in searchable)
    if matched_important:
        score += min(6, len(matched_important) * 2)
        reasons.append("mentions " + ", ".join(matched_important[:3]))
    if _is_today(message_date):
        score += 3
        reasons.append("received today")
    if _is_recent(message_date, days=7):
        score += 1
    if not query_terms and score == 0:
        score = 1
    return score, reasons


def build_gmail_answer_prompt(question, results):
    snippets = []
    for index, result in enumerate(results, start=1):
        snippets.append(
            f"{index}. Sender: {result['sender']}\n"
            f"Subject: {result['subject']}\n"
            f"Date: {result['date']}\n"
            f"Why it may matter: {result['reason']}\n"
            f"Content: {result['content'][:1200]}"
        )
    return (
        "Answer the user's Gmail question using only these indexed email snippets.\n\n"
        f"USER QUESTION: {question}\n\n"
        "EMAIL SNIPPETS:\n"
        + "\n\n".join(snippets)
        + "\n\nRULES:\n"
        "- Return a concise ranked answer.\n"
        "- Include sender, subject, time/date, and why each email matters.\n"
        "- Do not invent emails or facts not present in the snippets.\n"
        "- If nothing looks important, say that clearly.\n"
    )


def build_gmail_reply_prompt(instruction, message):
    content = message.body or message.snippet
    return (
        "Write a Gmail reply draft using only the email context and the user's instruction.\n\n"
        f"USER INSTRUCTION: {instruction}\n\n"
        f"FROM: {message.sender}\n"
        f"SUBJECT: {message.subject}\n"
        f"DATE: {message.date}\n"
        f"EMAIL:\n{content[:2500]}\n\n"
        "RULES:\n"
        "- Return only the reply body.\n"
        "- Do not include subject, recipient, labels, explanations, or markdown fences.\n"
        "- Keep it concise, natural, and ready to send.\n"
    )


def format_local_gmail_summary(results):
    if not results:
        return "No matching Gmail messages found in the local index. Try syncing Gmail first."
    lines = ["Important Gmail messages:"]
    for index, result in enumerate(results[:5], start=1):
        lines.append(
            f"{index}. {result['sender']} - {result['subject']} ({result['date']})\n"
            f"   Reason: {result['reason']}"
        )
    return "\n".join(lines)


def _row_to_result(row, score, reasons):
    message_id, sender, subject, message_date, snippet, body, labels, unread, starred, important = row
    content = _clean_display_text(body or snippet)
    searchable = f"{sender} {subject} {snippet} {body}".lower()
    has_urgency_terms = any(term in searchable for term in IMPORTANT_TERMS)
    return {
        "message_id": message_id,
        "sender": _clean_sender(sender),
        "subject": _clean_display_text(subject or "(no subject)"),
        "date": _format_display_date(message_date),
        "content": content,
        "reason": ", ".join(reasons) if reasons else "recent email",
        "score": score,
        "important": bool(starred or important or has_urgency_terms),
    }


def _query_terms(query):
    ignored = {"a", "an", "any", "are", "do", "find", "gmail", "have", "i", "important", "mail", "mails", "me", "my", "the", "today", "what"}
    return [term for term in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(term) > 2 and term not in ignored]


def _extract_body(payload):
    parts = []
    _collect_text_parts(payload, parts)
    return "\n".join(part for part in parts if part).strip()


def _collect_text_parts(part, parts):
    mime_type = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")
    if data and mime_type in ("text/plain", "text/html"):
        decoded = _decode_base64url(data)
        parts.append(_strip_html(decoded) if mime_type == "text/html" else decoded)
    for child in part.get("parts", []) or []:
        _collect_text_parts(child, parts)


def _decode_base64url(data):
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8")).decode("utf-8", errors="replace")


def _strip_html(text):
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    return _clean_display_text(re.sub(r"<[^>]+>", " ", text))


def _normalize_date(value):
    if not value:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _is_today(value):
    if not value:
        return False
    try:
        return datetime.fromisoformat(value).date() == datetime.now(timezone.utc).date()
    except ValueError:
        return False


def _is_recent(value, days):
    if not value:
        return False
    try:
        message_date = datetime.fromisoformat(value)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - message_date).days <= days


def _format_display_date(value):
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value).astimezone()
    except ValueError:
        return value
    return parsed.strftime("%d %b %Y, %I:%M %p").lstrip("0")


def _clean_sender(sender):
    name, address = email.utils.parseaddr(sender or "")
    if name:
        return _clean_display_text(name)
    return _clean_display_text(address or sender or "")


def _clean_display_text(text):
    text = html.unescape(text or "")
    text = text.replace("\xa0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
