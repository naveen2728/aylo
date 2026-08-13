import unittest

from aylo_app.web_shortcuts import detect_open_shortcut


class WebShortcutTests(unittest.TestCase):
    def test_detects_common_open_commands(self):
        self.assertEqual(detect_open_shortcut("open YouTube"), "https://www.youtube.com/")
        self.assertEqual(detect_open_shortcut("show my gmail"), "https://mail.google.com/mail/u/0/#inbox")
        self.assertEqual(detect_open_shortcut("launch chat gpt"), "https://chatgpt.com/")
        self.assertEqual(detect_open_shortcut("open whats app"), "https://web.whatsapp.com/")

    def test_ignores_non_open_requests(self):
        self.assertIsNone(detect_open_shortcut("write an email about youtube"))
        self.assertIsNone(detect_open_shortcut("find important gmail messages"))


if __name__ == "__main__":
    unittest.main()
