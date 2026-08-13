import json
import os
import tempfile
import unittest

from aylo_app.plugins import load_plugins, match_plugin_for_window


class PluginTests(unittest.TestCase):
    def test_builtin_gmail_plugin_matches_window_title(self):
        plugin = match_plugin_for_window("inbox - gmail - chrome.exe")
        self.assertEqual(plugin.plugin_id, "gmail")
        self.assertEqual(plugin.label, "Gmail")

    def test_builtin_notion_plugin_matches_window_title(self):
        plugin = match_plugin_for_window("project plan notion.exe")
        self.assertEqual(plugin.plugin_id, "notion")
        self.assertEqual(plugin.label, "Notion")

    def test_unknown_window_uses_default_plugin(self):
        plugin = match_plugin_for_window("unknown application")
        self.assertEqual(plugin.plugin_id, "default")

    def test_loads_custom_json_plugins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "linear.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "id": "linear",
                        "label": "Linear",
                        "keywords": ["linear"],
                        "cleanup_prompt": "Turn dictation into a concise issue comment.",
                    },
                    handle,
                )

            plugins = load_plugins(directory)
            plugin = match_plugin_for_window("linear app", plugins)
            self.assertEqual(plugin.plugin_id, "linear")
            self.assertEqual(plugin.cleanup_prompt, "Turn dictation into a concise issue comment.")

    def test_ignores_invalid_custom_plugins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "broken.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{broken")

            plugins = load_plugins(directory)
            self.assertTrue(all(plugin.plugin_id != "broken" for plugin in plugins))


if __name__ == "__main__":
    unittest.main()
