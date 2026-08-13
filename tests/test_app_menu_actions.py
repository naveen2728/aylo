import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from aylo_app.app import AyloApp
from aylo_app.config import AppSettings


class AppMenuActionTests(unittest.TestCase):
    def make_app(self):
        with patch("aylo_app.app.load_settings", return_value=AppSettings()), patch("aylo_app.app.HistoryStore"):
            app = AyloApp()
        app.overlay = Mock()
        app.show_toast = Mock()
        app.log_error = Mock()
        return app

    def test_clear_history_after_confirmation(self):
        app = self.make_app()
        with patch("aylo_app.app.messagebox.askyesno", return_value=True):
            app.clear_history()
        app.history.clear.assert_called_once_with()
        app.show_toast.assert_called_once_with("Recent results cleared.")

    def test_toggle_startup_enables_disabled_setting(self):
        app = self.make_app()
        with patch("aylo_app.app.is_startup_enabled", return_value=False), patch("aylo_app.app.set_startup_enabled") as set_enabled:
            app.toggle_startup()
        set_enabled.assert_called_once_with(True)
        app.show_toast.assert_called_once_with("Launch at startup enabled.")

    def test_open_gmail_opens_browser(self):
        app = self.make_app()
        with patch("webbrowser.open") as open_browser:
            app.open_gmail()
        open_browser.assert_called_once_with("https://mail.google.com/mail/u/0/#inbox")
        app.show_toast.assert_called_once_with("Opening site.")

    def test_ai_chat_uses_history_when_available(self):
        app = self.make_app()
        app.state.client = object()
        history = [{"role": "user", "content": "hello"}]
        with patch("aylo_app.app.ai_client.chat", return_value="hi") as chat:
            app._send_ai_chat("hello", history)
        chat.assert_called_once_with(app.state.client, history, app.log_error)
        app.overlay.show_ai_chat_reply.assert_called_once_with("hi")

    def test_ai_chat_reports_disconnected_ai(self):
        app = self.make_app()
        app.state.client = None
        with patch.dict(os.environ, {}, clear=True):
            app._send_ai_chat("hello", [])
        app.overlay.show_ai_chat_reply.assert_called_once_with(
            "AI is not connected. Update your API key or check your internet connection."
        )

    def test_ai_chat_reconnects_when_client_missing(self):
        app = self.make_app()
        app.state.client = None
        client = object()
        history = [{"role": "user", "content": "hello"}]
        with patch.dict(os.environ, {"GROQ_API_KEY": "key"}, clear=True), patch(
            "aylo_app.app.ai_client.connect", return_value=client
        ) as connect, patch("aylo_app.app.ai_client.chat", return_value="hi") as chat:
            app._send_ai_chat("hello", history)
        connect.assert_called_once_with()
        chat.assert_called_once_with(client, history, app.log_error)
        app.overlay.show_ai_chat_reply.assert_called_once_with("hi")

    def test_reconnect_ai_connects_saved_key(self):
        app = self.make_app()
        client = object()
        with patch("aylo_app.app.load_api_key", return_value="key"), patch(
            "aylo_app.app.ai_client.connect", return_value=client
        ) as connect:
            message = app.reconnect_ai()
        self.assertEqual(message, "AI connected.")
        self.assertIs(app.state.client, client)
        self.assertTrue(app.state.ai_cleanup)
        connect.assert_called_once_with()

    def test_reconnect_ai_reports_missing_key(self):
        app = self.make_app()
        with patch("aylo_app.app.load_api_key", return_value=None):
            message = app.reconnect_ai()
        self.assertIn("No Groq API key", message)

    def test_diagnostics_status_reports_core_services(self):
        app = self.make_app()
        app.state.client = object()
        app.state.model = object()
        app.state.stream = object()
        app.hotkeys = object()
        with patch("aylo_app.app.load_api_key", return_value="key"), patch.object(app, "_last_error_summary", return_value=""):
            rows = app.diagnostics_status()
        statuses = {label: value for label, value, ok in rows}
        self.assertEqual(statuses["Groq key"], "Found")
        self.assertEqual(statuses["AI client"], "Connected")
        self.assertEqual(statuses["Microphone"], "Open")

    def test_finish_onboarding_persists_flag(self):
        app = self.make_app()
        with patch("aylo_app.app.save_settings") as save_settings:
            app.finish_onboarding()
        self.assertTrue(app.state.settings.first_run_complete)
        save_settings.assert_called_once_with(app.state.settings)
        app.show_toast.assert_called_once_with("Aylo setup complete.")

    def test_ask_screen_uses_vision_client(self):
        app = self.make_app()
        app.state.client = object()
        with patch("aylo_app.app.ai_client.read_screen", return_value="screen answer") as read_screen:
            result = app.ask_screen_context("What is on screen?", "screen.png")
        self.assertEqual(result, "screen answer")
        read_screen.assert_called_once_with(app.state.client, "What is on screen?", "screen.png", app.log_error)
        app.history.add.assert_called_once()

    def test_ai_chat_generates_image_for_picture_request(self):
        app = self.make_app()
        with patch("aylo_app.app.generate_image", return_value="image.jpg") as generate_image, patch(
            "aylo_app.app.ai_client.chat"
        ) as chat:
            app._send_ai_chat("generate a picture of a clean desk setup", [])
        generate_image.assert_called_once_with("a clean desk setup")
        chat.assert_not_called()
        app.overlay.show_ai_chat_image.assert_called_once_with("image.jpg", "Generated image: a clean desk setup")
        app.history.add.assert_called_once()

    def test_capture_screen_hides_aylo_windows(self):
        app = self.make_app()
        root = Mock()
        root.winfo_exists.return_value = True
        root.state.return_value = "normal"
        ai_panel = Mock()
        ai_panel.winfo_exists.return_value = True
        ai_panel.state.return_value = "normal"
        app.overlay = SimpleNamespace(root=root, ai_panel=ai_panel, gmail_panel=None)
        image = Mock()
        with tempfile.TemporaryDirectory() as temp_dir, patch("aylo_app.app.appdata_dir", return_value=temp_dir), patch(
            "aylo_app.app.time.time", return_value=123
        ), patch("aylo_app.app.time.sleep"), patch("pyautogui.screenshot", return_value=image):
            path = app.capture_screen_context()
        self.assertTrue(path.endswith("screen-123.png"))
        ai_panel.withdraw.assert_called_once_with()
        root.withdraw.assert_called_once_with()
        image.save.assert_called_once_with(path)
        ai_panel.deiconify.assert_called_once_with()
        root.deiconify.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
