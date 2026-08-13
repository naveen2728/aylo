MAX_CLIPBOARD_LINES = 100


class ClipboardContentError(ValueError):
    pass


def line_count(text):
    if not text:
        return 0
    return text.count("\n") + 1


def validate_clipboard_content(text, min_characters=2):
    if not text or len(text.strip()) < min_characters:
        raise ClipboardContentError("Clipboard is empty. Copy text first.")
    lines = line_count(text)
    if lines > MAX_CLIPBOARD_LINES:
        raise ClipboardContentError(
            f"Copied content is {lines} lines. Copy 100 lines or fewer and try again."
        )
    return text
