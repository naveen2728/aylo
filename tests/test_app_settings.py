import unittest
from unittest.mock import Mock, patch

from aylo_app.app import AyloApp


class AppSettingsTests(unittest.TestCase):
    def test_failed_microphone_change_keeps_previous_device(self):
        with patch("aylo_app.app.load_settings") as load_settings, patch("aylo_app.app.HistoryStore"):
            settings = load_settings.return_value
            settings.samplerate = 16000
            settings.mic_device = 1
            settings.pre_buffer_seconds = 0.3
            settings.max_record_seconds = 30
            settings.min_record_seconds = 0.3
            settings.silence_rms_threshold = 0.002
            settings.mouse_side_button_mic = False
            settings.mouse_forward_action = "command"
            app = AyloApp()
        app.state.stream = object()

        with patch("aylo_app.app.open_input_stream", side_effect=RuntimeError("unavailable")):
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                app.apply_settings(mic_device=2, silence_rms_threshold=0.005, max_record_seconds=45)

        self.assertEqual(app.state.mic_device, 1)
        self.assertEqual(app.state.settings.mic_device, 1)

    def test_mouse_button_setting_refreshes_hotkey_listener(self):
        with patch("aylo_app.app.load_settings") as load_settings, patch("aylo_app.app.HistoryStore"):
            settings = load_settings.return_value
            settings.samplerate = 16000
            settings.mic_device = 1
            settings.pre_buffer_seconds = 0.3
            settings.max_record_seconds = 30
            settings.min_record_seconds = 0.3
            settings.silence_rms_threshold = 0.002
            settings.mouse_side_button_mic = False
            settings.mouse_forward_action = "command"
            app = AyloApp()
        app.state.stream = object()
        app.hotkeys = Mock()

        with patch("aylo_app.app.save_settings") as save_settings:
            app.apply_settings(
                mic_device=1,
                silence_rms_threshold=0.005,
                max_record_seconds=45,
                mouse_side_button_mic=True,
                mouse_forward_action="command",
            )

        self.assertTrue(app.state.settings.mouse_side_button_mic)
        self.assertEqual(app.state.settings.mouse_forward_action, "command")
        save_settings.assert_called_once_with(app.state.settings)
        app.hotkeys.refresh_mouse_listener.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
