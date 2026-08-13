import re


EXPLICIT_CLIPBOARD_WORDS = [
    "copied", "copy", "clipboard", "clip board", "selected", "selection",
]

REFERENCED_CONTENT_PHRASES = [
    "fix this", "change this", "modify this", "update this", "rewrite this",
    "refactor this", "optimize this", "clean this up", "improve this",
    "convert this", "transform this", "format this", "reformat this",
    "add to this", "remove from this", "delete from this",
    "remove this", "delete this", "take this out", "make this",
    "turn this into", "explain this", "summarize this", "translate this",
    "correct this", "shorten this", "expand this", "humanize this",
    "this code", "this function", "this class", "this script", "this file",
    "this snippet", "this block", "this sentence", "this text",
    "this message", "this email", "the selected text", "the selected code",
    "fix it", "change it", "modify it", "update it", "rewrite it",
    "refactor it", "optimize it", "clean it up", "improve it",
    "convert it", "transform it", "format it", "reformat it",
    "make it", "translate it", "summarize it", "shorten it",
    "fix that", "change that", "modify that", "update that", "rewrite that",
    "refactor that", "optimize that", "improve that", "convert that",
    "transform that", "format that", "translate that", "summarize that",
]

COMMAND_ACTIONS = {
    "convert": ["convert", "change", "transform", "rewrite", "to"],
    "add": ["add", "insert", "include", "put"],
    "create": ["create", "make", "generate", "build", "write"],
    "fix": ["fix", "debug", "repair", "solve", "correct"],
    "explain": ["explain", "describe", "what does", "how does"],
    "remove": ["remove", "delete", "take out", "get rid of"],
    "optimize": ["optimize", "improve", "faster", "better", "efficient"],
}


def should_use_clipboard(user_text):
    normalized = re.sub(r"[^a-z0-9]+", " ", user_text.lower()).strip()
    padded = f" {normalized} "
    return any(f" {word} " in padded for word in EXPLICIT_CLIPBOARD_WORDS) or any(
        f" {phrase} " in padded for phrase in REFERENCED_CONTENT_PHRASES
    )


def looks_like_code(text):
    if not text or len(text.strip()) < 5:
        return False
    indicators = [
        "def ", "class ", "import ", "from ", "function", "const ", "let ",
        "var ", "return", "if ", "for ", "while ", "{", "}", ";", "=>",
        "self.", "__init__", "print(", "console.", "</?", "#include",
        "public ", "private ", "static ", "void ", "int ", "string ",
    ]
    return any(indicator in text for indicator in indicators)


def detect_command_action(text):
    text_lower = text.lower()
    for action, keywords in COMMAND_ACTIONS.items():
        if any(keyword in text_lower for keyword in keywords):
            return action
    return "general"


def build_clipboard_prompt(user_text, clipboard_content):
    action = detect_command_action(user_text)
    lines = clipboard_content.count("\n")
    if lines > 30:
        size_instruction = f"The clipboard content is large ({lines} lines). Keep the response focused on the user's request."
    else:
        size_instruction = "Return the complete requested result."
    return (
        "You are a helpful assistant. The user has copied content to their clipboard "
        "and spoken a command. The clipboard may contain text, an email, a message, or code.\n\n"
        f"USER COMMAND: {user_text}\n"
        f"DETECTED ACTION: {action}\n\n"
        f"CLIPBOARD CONTENT:\n```\n{clipboard_content}\n```\n\n"
        "RULES:\n"
        f"- {size_instruction}\n"
        "- Do not add explanations, markdown fences, or preamble.\n"
        "- Follow the spoken command using the clipboard content as the input.\n"
        "- For code edits, preserve indentation, style, language, and conventions.\n"
        "- For writing edits, return only the rewritten or translated text.\n"
        "- If the command is impossible or unclear, return the clipboard content unchanged.\n"
    )


def build_standalone_prompt(user_text):
    action = detect_command_action(user_text)
    return (
        "You are a helpful assistant. The user has spoken a request.\n\n"
        f"USER REQUEST: {user_text}\n"
        f"DETECTED ACTION: {action}\n\n"
        "RULES:\n"
        "- Return ONLY the output - the message, text, or code the user asked for.\n"
        "- Do not add explanations, markdown fences, labels, or preamble.\n"
        "- Match the tone and style implied by the request "
        "(casual for chat messages, professional for emails, etc.).\n"
        "- If generating code, include necessary imports and make it ready to use.\n"
        "- Keep the output concise and complete.\n"
    )
