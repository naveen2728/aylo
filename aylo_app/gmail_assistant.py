from .gmail_index import GmailIndex, build_gmail_answer_prompt, build_gmail_reply_prompt, format_local_gmail_summary
import re


GMAIL_QUESTION_PHRASES = [
    "gmail", "mail", "mails", "email", "emails", "inbox",
]

GMAIL_ACTION_PHRASES = [
    "important", "unread", "summarize", "summary", "find", "search",
    "client", "today", "this week", "received", "sent",
]


def is_open_gmail_command(text):
    normalized = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()
    normalized = normalized.replace("g mail", "gmail").replace("gee mail", "gmail")
    words = set(normalized.split())
    open_words = {"open", "show", "display", "view"}
    gmail_words = {"gmail", "mail", "mails", "email", "emails", "inbox"}
    blocked_words = {"important", "unread", "summarize", "summary", "find", "search", "from"}
    return bool(words & open_words) and bool(words & gmail_words) and not bool(words & blocked_words)


def is_gmail_question(text):
    normalized = (text or "").lower()
    return any(phrase in normalized for phrase in GMAIL_QUESTION_PHRASES) and any(
        phrase in normalized for phrase in GMAIL_ACTION_PHRASES
    )


def answer_gmail_question(question, ai_client=None, log_error=None, index=None):
    index = index or GmailIndex()
    results = search_gmail(question, index=index)
    if not results:
        return format_local_gmail_summary(results)
    if ai_client is None:
        return format_local_gmail_summary(results)

    from . import ai_client as ai_module

    prompt = build_gmail_answer_prompt(question, results)
    return ai_module.generate(ai_client, prompt, log_error or (lambda *_: None))


def search_gmail(question, index=None, limit=8):
    index = index or GmailIndex()
    return index.search(question, limit=limit)


def generate_gmail_reply(instruction, message_id, ai_client, log_error=None, index=None):
    if ai_client is None:
        raise RuntimeError("No API key. Set it from the context menu.")
    index = index or GmailIndex()
    message = index.get_message(message_id)
    if message is None:
        raise RuntimeError("Could not find that email in the local Gmail index. Sync Gmail and try again.")

    from . import ai_client as ai_module

    prompt = build_gmail_reply_prompt(instruction, message)
    return message, ai_module.generate(ai_client, prompt, log_error or (lambda *_: None))
