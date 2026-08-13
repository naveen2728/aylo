import json
import os
import tempfile
import unittest

from aylo_app.history import HistoryEntry, HistoryStore, history_label


class HistoryTests(unittest.TestCase):
    def test_newest_entry_is_first_and_store_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.json")
            store = HistoryStore(path, max_entries=3)
            for number in range(5):
                store.add(f"result {number}", mode="dictation")
            self.assertEqual([entry.text for entry in store.list_entries()], ["result 4", "result 3", "result 2"])

    def test_persists_command_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.json")
            HistoryStore(path).add("translated text", mode="command", used_clipboard=True, request="translate copied text")
            entry = HistoryStore(path).list_entries()[0]
            self.assertEqual(entry.text, "translated text")
            self.assertEqual(entry.mode, "command")
            self.assertTrue(entry.used_clipboard)
            self.assertEqual(entry.request, "translate copied text")

    def test_recovers_from_invalid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"unexpected": True}, handle)
            self.assertEqual(HistoryStore(path).list_entries(), [])

    def test_clear_removes_persisted_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "history.json")
            store = HistoryStore(path)
            store.add("temporary result", mode="dictation")
            store.clear()
            self.assertEqual(HistoryStore(path).list_entries(), [])

    def test_history_label_is_compact(self):
        entry = HistoryEntry(text="one   two\nthree " + ("x" * 80), mode="command", timestamp="")
        label = history_label(entry, max_length=24)
        self.assertTrue(label.startswith("command: one two three"))
        self.assertTrue(label.endswith("..."))


if __name__ == "__main__":
    unittest.main()
