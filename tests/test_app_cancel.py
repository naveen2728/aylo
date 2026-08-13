import unittest
from unittest.mock import Mock, patch

from aylo_app.app import AyloApp
from aylo_app.config import AppSettings
from aylo_app.state import STATE_IDLE, STATE_RECORDING


class AppCancelTests(unittest.TestCase):
    def test_cancel_discards_recording_and_timer(self):
        with patch("aylo_app.app.load_settings", return_value=AppSettings()), patch("aylo_app.app.HistoryStore"):
            app = AyloApp()
        timer = Mock()
        app.state.recording_state = STATE_RECORDING
        app.state.audio_frames = ["captured audio"]
        app.state.max_record_timer = timer
        app.set_orb = Mock()
        app.show_toast = Mock()

        app.cancel_recording()

        self.assertEqual(app.state.recording_state, STATE_IDLE)
        self.assertEqual(app.state.audio_frames, [])
        self.assertIsNone(app.state.max_record_timer)
        timer.cancel.assert_called_once_with()
        app.show_toast.assert_called_once_with("Recording cancelled.")


if __name__ == "__main__":
    unittest.main()
