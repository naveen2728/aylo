import unittest

from aylo_app.overlay import AI_INPUT_FONT_SIZE, AI_PENDING_FONT_SIZE, AI_REPLY_FONT_SIZE, format_chat_display_text, thinking_display_text


class OverlayTextTests(unittest.TestCase):
    def test_removes_markdown_emphasis_and_headings(self):
        source = "## Response A\n**Conclusion:** This is *better*."
        self.assertEqual(format_chat_display_text(source), "Response A\nConclusion: This is better.")

    def test_formats_markdown_lists_for_display(self):
        source = "1. First item\n2) Second item\n- Final item"
        self.assertEqual(format_chat_display_text(source), "• First item\n• Second item\n• Final item")

    def test_preserves_paragraph_spacing(self):
        source = "First paragraph.\n\n\n\nSecond paragraph."
        self.assertEqual(format_chat_display_text(source), "First paragraph.\n\nSecond paragraph.")

    def test_thinking_text_cycles_animated_dots(self):
        self.assertEqual([thinking_display_text("Thinking...", step) for step in range(5)], ["Thinking", "Thinking.", "Thinking..", "Thinking...", "Thinking"])

    def test_reading_state_uses_same_animation_format(self):
        self.assertEqual(thinking_display_text("Reading screenshot", 2), "Reading screenshot..")

    def test_ai_chat_fonts_are_large_and_readable(self):
        self.assertGreaterEqual(AI_INPUT_FONT_SIZE, 14)
        self.assertGreaterEqual(AI_REPLY_FONT_SIZE, 16)
        self.assertGreaterEqual(AI_PENDING_FONT_SIZE, 15)


if __name__ == "__main__":
    unittest.main()
