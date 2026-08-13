import unittest
from unittest.mock import Mock, call, patch

from aylo_app.app import AyloApp, enable_dpi_awareness
from aylo_app.ai_client import GenerationError
from aylo_app.config import AppSettings
from aylo_app.state import STATE_IDLE, STATE_RECORDING


class AppCommandTests(unittest.TestCase):
    def test_enable_dpi_awareness_is_safe_to_call(self):
        enable_dpi_awareness()

    def make_app(self):
        with patch("aylo_app.app.load_settings", return_value=AppSettings(ai_features_enabled=True)), patch("aylo_app.app.HistoryStore"):
            app = AyloApp()
        app.state.client = object()
        app.state.clipboard_snapshot = "def old():\n    return 1"
        app.show_toast = Mock()
        app.set_orb = Mock()
        app._record_history = Mock()
        app._transcribe = Mock(return_value="Change it to return two")
        return app

    def test_ai_command_is_blocked_when_ai_features_are_off(self):
        app = self.make_app()
        app.state.settings.ai_features_enabled = False
        app._process_command([])
        app._transcribe.assert_not_called()
        app.show_toast.assert_called_once_with("AI Features are off. Enable them in Settings.")

    def test_shift_command_uses_clipboard_for_natural_it_reference(self):
        app = self.make_app()
        with patch("pyperclip.paste", return_value="def old():\n    return 1"), patch("pyperclip.copy") as copy, patch("pyautogui.hotkey"), patch("aylo_app.app.ai_client.generate", return_value="def old():\n    return 2") as generate, patch("aylo_app.app.time.sleep"):
            app._process_command([])
        prompt = generate.call_args.args[1]
        self.assertIn("CLIPBOARD CONTENT", prompt)
        self.assertIn("def old():", prompt)
        self.assertEqual(
            copy.call_args_list,
            [call("def old():\n    return 2"), call("def old():\n    return 1")],
        )
        app._record_history.assert_called_once_with(
            "def old():\n    return 2",
            mode="command",
            used_clipboard=True,
            request="Change it to return two",
        )

    def test_shift_command_rejects_more_than_100_clipboard_lines(self):
        app = self.make_app()
        app.state.clipboard_snapshot = "\n".join(f"line {number}" for number in range(101))
        with patch("aylo_app.app.ai_client.generate") as generate:
            app._process_command([])
        generate.assert_not_called()
        app.show_toast.assert_any_call("Copied content is 101 lines. Copy 100 lines or fewer and try again.")

    def test_shift_command_surfaces_friendly_ai_error(self):
        app = self.make_app()
        with patch("aylo_app.app.ai_client.generate", side_effect=GenerationError("Groq API key is invalid. Update it from the context menu.")), patch("pyperclip.copy") as copy:
            app._process_command([])
        copy.assert_not_called()
        app.show_toast.assert_any_call("Groq API key is invalid. Update it from the context menu.")

    def test_shift_command_reconnects_when_startup_api_connect_failed(self):
        app = self.make_app()
        app.state.client = None
        client = object()
        with patch("aylo_app.app.load_api_key", return_value="key"), patch(
            "aylo_app.app.ai_client.connect", return_value=client
        ) as connect, patch("aylo_app.app.ai_client.generate", return_value="done") as generate, patch(
            "pyperclip.copy"
        ), patch("pyautogui.hotkey"), patch("aylo_app.app.time.sleep"):
            app._process_command([])
        connect.assert_called_once_with()
        self.assertIs(app.state.client, client)
        generate.assert_called_once()
        app.show_toast.assert_not_called()

    def test_dictation_can_open_web_shortcut(self):
        app = self.make_app()
        app._transcribe = Mock(return_value="open youtube")
        app.open_web_shortcut = Mock()
        with patch("aylo_app.app.ai_client.cleanup") as cleanup, patch("pyperclip.copy") as copy:
            app._process_dictation([], "prompt")
        app.open_web_shortcut.assert_called_once_with("https://www.youtube.com/")
        cleanup.assert_not_called()
        copy.assert_not_called()

    def test_dictation_never_uses_ai_cleanup(self):
        app = self.make_app()
        app._transcribe = Mock(return_value="plain local dictation")
        app._paste_text_preserving_clipboard = Mock()
        with patch("aylo_app.app.ai_client.cleanup") as cleanup:
            app._process_dictation([], "prompt")
        cleanup.assert_not_called()
        app._paste_text_preserving_clipboard.assert_called_once_with("plain local dictation", release_keys=("shift",))

    def test_voice_chat_speaks_ai_response_without_pasting(self):
        app = self.make_app()
        app._transcribe = Mock(return_value="tell me a tiny joke")
        with patch("aylo_app.app.ai_client.chat", return_value="A tiny joke."), patch(
            "aylo_app.app.speak_text"
        ) as speak, patch("pyperclip.copy") as copy, patch("pyautogui.hotkey") as hotkey:
            app._process_voice_chat([])
        speak.assert_called_once_with("A tiny joke.")
        copy.assert_not_called()
        hotkey.assert_not_called()
        app._record_history.assert_called_once_with(
            "A tiny joke.",
            mode="voice-chat",
            request="tell me a tiny joke",
        )

    def test_start_voice_chat_starts_realtime_agent(self):
        app = self.make_app()
        with patch("aylo_app.app.load_openai_realtime_api_key", return_value="openai-key"), patch(
            "aylo_app.app.RealtimeVoiceAgent"
        ) as agent_class:
            app.start_voice_chat()
        self.assertTrue(app.voice_chat_active)
        agent_class.assert_called_once_with("openai-key", app.log_error, app._realtime_voice_status)
        agent_class.return_value.start.assert_called_once_with()
        app.set_orb.assert_called_with("recording")
        app.show_toast.assert_called_once_with("Realtime voice chat started. Speak anytime to interrupt.", duration=4000)

    def test_start_voice_chat_prompts_for_missing_realtime_key(self):
        app = self.make_app()
        app.change_openai_realtime_api_key = Mock()
        with patch("aylo_app.app.load_openai_realtime_api_key", side_effect=[None, None]), patch(
            "aylo_app.app.RealtimeVoiceAgent"
        ) as agent_class:
            app.start_voice_chat()
        self.assertFalse(app.voice_chat_active)
        app.change_openai_realtime_api_key.assert_called_once_with()
        agent_class.assert_not_called()
        app.show_toast.assert_called_once_with("Add an OpenAI Realtime API key first.", duration=4000)

    def test_start_voice_chat_rejects_current_recording(self):
        app = self.make_app()
        app.state.recording_state = STATE_RECORDING
        with patch("aylo_app.app.RealtimeVoiceAgent") as agent_class:
            app.start_voice_chat()
        self.assertFalse(app.voice_chat_active)
        agent_class.assert_not_called()
        app.show_toast.assert_called_once_with("Finish the current recording first.")

    def test_stop_voice_chat_stops_realtime_agent(self):
        app = self.make_app()
        app.voice_chat_active = True
        app.realtime_voice_agent = Mock()
        app.stop_voice_chat()
        self.assertFalse(app.voice_chat_active)
        self.assertIsNone(app.realtime_voice_agent)
        app.set_orb.assert_called_once_with("idle")
        app.show_toast.assert_called_once_with("Realtime voice chat stopped.")

    def test_realtime_voice_failure_status_resets_menu_state(self):
        app = self.make_app()
        app.voice_chat_active = True
        app.realtime_voice_agent = object()
        app._realtime_voice_status("Realtime voice connection failed.")
        self.assertFalse(app.voice_chat_active)
        self.assertIsNone(app.realtime_voice_agent)
        app.set_orb.assert_called_once_with("idle")
        app.show_toast.assert_called_once_with("Realtime voice connection failed.", duration=3000)
        self.assertEqual(app.state.recording_state, STATE_IDLE)


if __name__ == "__main__":
    unittest.main()
