import unittest

from aylo_app.prompts import get_prompt_for_window


class PromptTests(unittest.TestCase):
    def test_email_prompt(self):
        _, label = get_prompt_for_window("inbox gmail chrome.exe")
        self.assertEqual(label, "Gmail")

    def test_default_prompt(self):
        _, label = get_prompt_for_window("unknown application")
        self.assertEqual(label, "Default")


if __name__ == "__main__":
    unittest.main()
