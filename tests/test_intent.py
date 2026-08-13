import unittest

from aylo_app.intent import (
    build_clipboard_prompt,
    detect_command_action,
    looks_like_code,
    should_use_clipboard,
)


class IntentTests(unittest.TestCase):
    def test_detects_clipboard_request(self):
        self.assertTrue(should_use_clipboard("Please fix this function"))
        self.assertFalse(should_use_clipboard("Write a short email"))

    def test_detects_natural_copied_content_requests(self):
        requests = [
            "There is a copied code edit this code into this way",
            "Change my sentence into correct format which I have copied",
            "Translate the clipboard message to Hindi",
            "Summarize the selected text",
            "Use the clip board content and write a reply",
            "Make it into a good version",
            "Change it to use a loop",
            "Translate that into Hindi",
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assertTrue(should_use_clipboard(request))

    def test_does_not_attach_clipboard_for_standalone_generation(self):
        requests = [
            "Write Python code for a calculator",
            "Write a professional email asking for leave",
            "Translate hello to Hindi",
            "Write copywriting tips for a landing page",
            "Create a copyright notice",
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assertFalse(should_use_clipboard(request))

    def test_detects_action(self):
        self.assertEqual(detect_command_action("Optimize this function"), "optimize")
        self.assertEqual(detect_command_action("Say hello"), "general")

    def test_detects_code(self):
        self.assertTrue(looks_like_code("def greet():\n    return 'hello'"))
        self.assertFalse(looks_like_code("hello there"))

    def test_clipboard_prompt_contains_command_and_code(self):
        prompt = build_clipboard_prompt("fix this", "def broken(:")
        self.assertIn("USER COMMAND: fix this", prompt)
        self.assertIn("def broken(:", prompt)

    def test_clipboard_prompt_supports_regular_text(self):
        prompt = build_clipboard_prompt("correct the copied sentence", "i am reach there")
        self.assertIn("email, a message, or code", prompt)
        self.assertIn("i am reach there", prompt)


if __name__ == "__main__":
    unittest.main()
