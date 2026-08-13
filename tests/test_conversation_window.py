import unittest

from aylo_app.conversation_window import ConversationWindow


class ConversationWindowTranscriptTests(unittest.TestCase):
    def setUp(self):
        self.window = ConversationWindow(None, lambda _callback: None, lambda: None, lambda _muted: None)
        self.window._render = lambda: None

    def test_streamed_delta_keeps_word_spacing(self):
        self.window._update_transcript({"role": "assistant", "text": "Hello", "final": False})
        self.window._update_transcript({"role": "assistant", "text": " there", "final": False})
        self.window._update_transcript({"role": "assistant", "text": "Hello there", "final": True})

        self.assertEqual(self.window.messages, [{"role": "assistant", "text": "Hello there", "system": False}])
        self.assertIsNone(self.window.active["assistant"])

    def test_new_final_turn_creates_new_message(self):
        self.window._update_transcript({"role": "user", "text": "First", "final": True})
        self.window._update_transcript({"role": "user", "text": "Second", "final": True})

        self.assertEqual([message["text"] for message in self.window.messages], ["First", "Second"])


if __name__ == "__main__":
    unittest.main()
