import unittest

from aylo_app.rewrite_actions import REWRITE_ACTIONS, build_rewrite_prompt


class RewriteActionTests(unittest.TestCase):
    def test_presets_include_notes_and_humanize(self):
        labels = [label for label, _ in REWRITE_ACTIONS]
        self.assertIn("Turn into notes", labels)
        self.assertIn("Humanize", labels)

    def test_prompt_contains_instruction_and_clipboard_content(self):
        prompt = build_rewrite_prompt("Turn this into meeting notes", "Discuss launch date")
        self.assertIn("INSTRUCTION: Turn this into meeting notes", prompt)
        self.assertIn("Discuss launch date", prompt)
        self.assertIn("Return only the requested result", prompt)


if __name__ == "__main__":
    unittest.main()
