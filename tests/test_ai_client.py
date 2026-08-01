import unittest
from unittest.mock import Mock, patch

from voiceflow_app.ai_client import (
    CHAT_MODEL,
    GenerationError,
    VISION_MODEL,
    clean_chat_output,
    clean_generated_output,
    chat,
    friendly_generation_error,
    generate,
    read_screen,
    strip_reasoning_output,
)


class ApiError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class AiClientTests(unittest.TestCase):
    def test_strips_outer_markdown_code_fence(self):
        output = "```java\npublic class Main {}\n```"
        self.assertEqual(clean_generated_output(output), "public class Main {}")

    def test_keeps_plain_text_unchanged(self):
        self.assertEqual(clean_generated_output(" hello world "), "hello world")

    def test_strips_common_assistant_preamble(self):
        output = 'I can help with that.\n\n"Hey Dad, I will not be able to make it. Sorry about that."'
        self.assertEqual(clean_generated_output(output), "Hey Dad, I will not be able to make it. Sorry about that.")

    def test_strips_single_line_surrounding_quotes(self):
        self.assertEqual(clean_generated_output('"Hey Dad, I cannot make it."'), "Hey Dad, I cannot make it.")

    def test_keeps_valid_single_line_content_that_starts_similarly(self):
        self.assertEqual(clean_generated_output("Sure decisions take time."), "Sure decisions take time.")

    def test_chat_output_converts_markdown_asterisk_bullets_to_dot_bullets(self):
        output = "* First item\n  * Nested item\nNormal line"
        self.assertEqual(clean_chat_output(output), "• First item\n  • Nested item\nNormal line")

    def test_chat_output_normalizes_hyphen_and_plus_lists(self):
        self.assertEqual(clean_chat_output("- First\n+ Second"), "• First\n• Second")

    def test_strips_raw_reasoning_and_keeps_only_final_answer(self):
        output = "<think>Private image analysis.</think>\nThe app shows a settings page."
        self.assertEqual(strip_reasoning_output(output), "The app shows a settings page.")
        self.assertEqual(clean_chat_output(output), "The app shows a settings page.")

    def test_drops_truncated_reasoning_instead_of_exposing_it(self):
        self.assertEqual(strip_reasoning_output("<think>unfinished private reasoning"), "")

    def test_chat_uses_quality_model_and_consistent_prompt(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [Mock(message=Mock(content="Direct answer"))]
        self.assertEqual(chat(client, [{"role": "user", "content": "Question"}], Mock()), "Direct answer")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], CHAT_MODEL)
        self.assertIn("Start with the direct answer", kwargs["messages"][0]["content"])

    def test_classifies_common_groq_errors(self):
        self.assertIn("invalid", friendly_generation_error(ApiError("unauthorized", 401)))
        self.assertIn("too large", friendly_generation_error(ApiError("Request too large", 413)))
        self.assertIn("limit reached", friendly_generation_error(ApiError("rate_limit_exceeded", 429)))
        self.assertIn("connect", friendly_generation_error(ApiError("Connection timed out")))
        self.assertIn("model", friendly_generation_error(ApiError("model_not_found", 404)))

    def test_generate_raises_friendly_error_and_logs_original(self):
        client = Mock()
        client.chat.completions.create.side_effect = ApiError("Request too large", 413)
        log_error = Mock()
        with self.assertRaisesRegex(GenerationError, "too large"):
            generate(client, "prompt", log_error)
        log_error.assert_called_once()

    @patch("groq.Groq")
    def test_connect_can_validate_a_candidate_key(self, groq):
        from voiceflow_app.ai_client import connect

        client = connect(api_key="gsk_candidate")

        groq.assert_called_once_with(api_key="gsk_candidate")
        self.assertIs(client, groq.return_value)

    def test_generate_uses_answer_only_system_prompt(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="result"))
        ]
        self.assertEqual(generate(client, "prompt", Mock()), "result")
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("Never add acknowledgements", messages[0]["content"])

    def test_read_screen_sends_image_and_question_to_vision_model(self):
        client = Mock()
        client.chat.completions.create.return_value.choices = [
            Mock(message=Mock(content="The screen shows an error."))
        ]
        with patch("voiceflow_app.ai_client._image_data_url", return_value="data:image/jpeg;base64,abc"):
            result = read_screen(client, "What is wrong?", "screen.png", Mock())
        self.assertEqual(result, "The screen shows an error.")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], VISION_MODEL)
        self.assertEqual(kwargs["reasoning_format"], "hidden")
        self.assertEqual(kwargs["reasoning_effort"], "none")
        self.assertEqual(kwargs["temperature"], 0.3)
        content = kwargs["messages"][0]["content"]
        self.assertIn("What is wrong?", content[0]["text"])
        self.assertEqual(content[1]["image_url"]["url"], "data:image/jpeg;base64,abc")

    def test_read_screen_reports_when_the_current_vision_model_is_unavailable(self):
        client = Mock()
        client.chat.completions.create.side_effect = ApiError("model_not_found", 404)
        log_error = Mock()
        with patch("voiceflow_app.ai_client._image_data_url", return_value="data:image/jpeg;base64,abc"):
            with self.assertRaisesRegex(GenerationError, "model is unavailable"):
                read_screen(client, "What is wrong?", "screen.png", log_error)
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(log_error.call_count, 2)


if __name__ == "__main__":
    unittest.main()
