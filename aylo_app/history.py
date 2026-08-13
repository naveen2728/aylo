from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os


MAX_HISTORY_ENTRIES = 20


@dataclass
class HistoryEntry:
    text: str
    mode: str
    timestamp: str
    used_clipboard: bool = False
    request: str = ""


class HistoryStore:
    def __init__(self, path, max_entries=MAX_HISTORY_ENTRIES):
        self.path = path
        self.max_entries = max_entries
        self._entries = self._load()

    def add(self, text, mode, used_clipboard=False, request=""):
        if not text or not text.strip():
            return
        entry = HistoryEntry(
            text=text.strip(),
            mode=mode,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            used_clipboard=used_clipboard,
            request=request.strip(),
        )
        self._entries.insert(0, entry)
        self._entries = self._entries[: self.max_entries]
        self._save()

    def list_entries(self):
        return list(self._entries)

    def clear(self):
        self._entries = []
        self._save()

    def _load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if not isinstance(stored, list):
                return []
            entries = []
            for item in stored:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    continue
                entries.append(
                    HistoryEntry(
                        text=item["text"],
                        mode=item.get("mode", "unknown"),
                        timestamp=item.get("timestamp", ""),
                        used_clipboard=bool(item.get("used_clipboard", False)),
                        request=item.get("request", ""),
                    )
                )
            return entries[: self.max_entries]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return []

    def _save(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump([asdict(entry) for entry in self._entries], handle, indent=2)
            handle.write("\n")


def history_label(entry, max_length=54):
    preview = " ".join(entry.text.split())
    if len(preview) > max_length:
        preview = preview[: max_length - 3] + "..."
    return f"{entry.mode}: {preview}"
