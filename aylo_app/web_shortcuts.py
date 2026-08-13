import re


OPEN_WORDS = {"open", "show", "display", "view", "launch"}

WEB_SHORTCUTS = {
    "gmail": "https://mail.google.com/mail/u/0/#inbox",
    "mail": "https://mail.google.com/mail/u/0/#inbox",
    "inbox": "https://mail.google.com/mail/u/0/#inbox",
    "youtube": "https://www.youtube.com/",
    "you tube": "https://www.youtube.com/",
    "google": "https://www.google.com/",
    "notion": "https://www.notion.so/",
    "chatgpt": "https://chatgpt.com/",
    "chat gpt": "https://chatgpt.com/",
    "instagram": "https://www.instagram.com/",
    "whatsapp": "https://web.whatsapp.com/",
    "whats app": "https://web.whatsapp.com/",
    "twitter": "https://x.com/",
    "x": "https://x.com/",
    "github": "https://github.com/",
    "git hub": "https://github.com/",
}


def detect_open_shortcut(text):
    normalized = _normalize(text)
    if not normalized:
        return None
    words = set(normalized.split())
    if not words & OPEN_WORDS:
        return None
    for label in sorted(WEB_SHORTCUTS, key=len, reverse=True):
        if _contains_phrase(normalized, label):
            return WEB_SHORTCUTS[label]
    return None


def _normalize(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _contains_phrase(text, phrase):
    return re.search(rf"(^| ){re.escape(phrase)}($| )", text) is not None
