from dataclasses import dataclass
import json
import os

from .config import appdata_dir


@dataclass(frozen=True)
class AppPlugin:
    plugin_id: str
    label: str
    keywords: tuple[str, ...]
    cleanup_prompt: str
    enabled: bool = True


BUILTIN_PLUGINS = [
    AppPlugin(
        "gmail",
        "Gmail",
        ("gmail", "mail.google.com"),
        "Fix grammar, punctuation, and capitalization. Remove filler words. Preserve the user's tone and email structure. Return only the finished email text.",
    ),
    AppPlugin(
        "outlook",
        "Outlook",
        ("outlook", "office mail", "new message"),
        "Fix grammar, punctuation, and capitalization. Keep the message professional and concise. Return only the finished email text.",
    ),
    AppPlugin(
        "notion",
        "Notion",
        ("notion",),
        "Fix grammar, punctuation, and capitalization. Organize rough dictation into clean notes when appropriate. Preserve headings, bullets, and tasks. Return only the finished note text.",
    ),
    AppPlugin(
        "docs",
        "Docs",
        ("docs", "word", "google docs"),
        "Fix punctuation, capitalization, and grammar. Remove filler words. Do not rewrite sentences unless needed for clarity. Return only corrected text.",
    ),
    AppPlugin(
        "chat",
        "Chat",
        ("whatsapp", "telegram", "discord", "slack"),
        "Fix spelling and grammar only. Do not reword or change tone. Return the exact message with errors corrected.",
    ),
    AppPlugin(
        "prompt",
        "Prompt",
        ("claude", "chatgpt", "cursor"),
        "Fix grammar and punctuation. Clarify unclear phrasing. Preserve the user's intent. Return only the improved prompt.",
    ),
    AppPlugin(
        "code",
        "Code",
        ("vscode", "visual studio code", "pycharm", "terminal"),
        "Fix punctuation and capitalization only. Do not change technical terms, identifiers, commands, or code structure. Return only corrected text.",
    ),
]

DEFAULT_PLUGIN = AppPlugin(
    "default",
    "Default",
    tuple(),
    "Fix punctuation, capitalization, and remove filler words. Do not rewrite. Return only corrected text.",
)


def plugins_dir():
    path = os.path.join(appdata_dir(), "plugins")
    os.makedirs(path, exist_ok=True)
    return path


def load_plugins(directory=None):
    plugins = list(BUILTIN_PLUGINS)
    directory = directory or plugins_dir()
    if not os.path.isdir(directory):
        return plugins

    for filename in sorted(os.listdir(directory)):
        if not filename.lower().endswith(".json"):
            continue
        plugin = _load_plugin_file(os.path.join(directory, filename))
        if plugin is not None:
            plugins.append(plugin)
    return plugins


def match_plugin_for_window(title, plugins=None):
    normalized_title = (title or "").lower()
    for plugin in plugins or load_plugins():
        if not plugin.enabled:
            continue
        if any(keyword in normalized_title for keyword in plugin.keywords):
            return plugin
    return DEFAULT_PLUGIN


def _load_plugin_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    try:
        plugin_id = _clean_required_text(data, "id")
        label = _clean_required_text(data, "label")
        cleanup_prompt = _clean_required_text(data, "cleanup_prompt")
        keywords = tuple(
            keyword.strip().lower()
            for keyword in data.get("keywords", [])
            if isinstance(keyword, str) and keyword.strip()
        )
    except (AttributeError, TypeError, ValueError):
        return None

    if not keywords:
        return None
    return AppPlugin(
        plugin_id=plugin_id,
        label=label,
        keywords=keywords,
        cleanup_prompt=cleanup_prompt,
        enabled=bool(data.get("enabled", True)),
    )


def _clean_required_text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Missing plugin field: {key}")
    return value.strip()
