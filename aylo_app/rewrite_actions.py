REWRITE_ACTIONS = [
    ("Fix grammar", "Fix grammar, spelling, and punctuation. Preserve the original meaning and tone."),
    ("Make professional", "Rewrite this in a clear, professional tone."),
    ("Make casual", "Rewrite this in a natural, casual tone."),
    ("Shorten", "Make this shorter and more concise while preserving the important information."),
    ("Humanize", "Rewrite this so it sounds natural and human, not robotic or overly formal."),
    ("Translate to Hindi", "Translate this to Hindi. Return only the translated text."),
    ("Summarize", "Summarize this clearly and concisely."),
    ("Turn into notes", "Turn this into organized notes with clear headings and bullet points where useful."),
]


def build_rewrite_prompt(instruction, clipboard_content):
    return (
        "You are editing content copied from the user's clipboard. "
        "The content may be a sentence, message, email, notes, or code.\n\n"
        f"INSTRUCTION: {instruction}\n\n"
        f"CLIPBOARD CONTENT:\n```\n{clipboard_content}\n```\n\n"
        "RULES:\n"
        "- Return only the requested result.\n"
        "- Do not add explanations, labels, preamble, or markdown fences.\n"
        "- Preserve the original meaning unless the instruction asks you to change it.\n"
        "- If the content is code, preserve indentation and coding style.\n"
    )
