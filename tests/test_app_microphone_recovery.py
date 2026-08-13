import unittest
from unittest.mock import Mock, patch

from aylo_app.app import AyloApp
from aylo_app.config import AppSettings
from aylo_app.state import STATE_RECORDING
from aylo_app.transcription import AudioQualityError


class AppMicrophoneRecoveryTests(unittest.TestCase):
    def make_app(self):
        with patch("aylo_app.app.load_settings", return_value=AppSettings()), patch("aylo_app.app.HistoryStore"):
            app = AyloApp()
        app.show_toast = Mock()
        app.set_orb = Mock()
        app.log_error = Mock()
        return app

    def test_stale_callback_reconnects_before_recording(self):
        app = self.make_app()
        app.state.stream = Mock(active=True)
        app.state.last_audio_callback_at = 5.0
        app._refresh_microphone_stream = Mock(return_value=True)
        with patch("aylo_app.app.time.monotonic", return_value=10.0), patch("aylo_app.app.threading.Timer"):
            app.start_recording()
        app._refresh_microphone_stream.assert_called_once_with("stale before recording")
        self.assertEqual(app.state.recording_state, STATE_RECORDING)

    def test_fresh_callback_does_not_reconnect(self):
        app = self.make_app()
        app.state.stream = Mock(active=True)
        app.state.last_audio_callback_at = 9.5
        app._refresh_microphone_stream = Mock(return_value=True)
        with patch("aylo_app.app.time.monotonic", return_value=10.0), patch("aylo_app.app.threading.Timer"):
            app.start_recording()
        app._refresh_microphone_stream.assert_not_called()

    def test_detects_when_recording_contains_only_prebuffer(self):
        app = self.make_app()
        app.state.input_samplerate = 48000
        app.state.input_blocksize = 960
        self.assertTrue(app._recording_stream_stalled(frame_count=17, prebuffer_frames=17, held_seconds=2.0))
        self.assertFalse(app._recording_stream_stalled(frame_count=110, prebuffer_frames=17, held_seconds=2.0))

    def test_short_release_defers_processing_until_minimum_capture_window(self):
        app = self.make_app()
        app.state.recording_state = STATE_RECORDING
        app.state.recording_started_at = 9.7
        app.state.recording_prebuffer_frames = 17
        app.state.audio_frames = [object()] * 30
        timer = Mock()
        with patch("aylo_app.app.time.monotonic", return_value=10.0), patch(
            "aylo_app.app.threading.Timer", return_value=timer
        ):
            app.stop_and_process()
        self.assertEqual(app.state.recording_state, STATE_RECORDING)
        self.assertIs(app.state.minimum_record_timer, timer)
        timer.start.assert_called_once_with()

    def test_stalled_recording_reconnects_instead_of_reporting_no_voice(self):
        app = self.make_app()
        app.state.recording_state = STATE_RECORDING
        app.state.audio_frames = [object()] * 17
        app.state.recording_prebuffer_frames = 17
        app.state.recording_started_at = 8.0
        app.state.input_samplerate = 48000
        app.state.input_blocksize = 960
        app._refresh_microphone_stream = Mock(return_value=True)
        with patch("aylo_app.app.time.monotonic", return_value=10.0):
            app.stop_and_process()
        app._refresh_microphone_stream.assert_called_once_with("recording stream stalled")
        app.show_toast.assert_called_once_with("Microphone reconnected. Hold Right Shift and speak again.")

    def test_refresh_replaces_stale_stream(self):
        app = self.make_app()
        old_stream = Mock()
        replacement = Mock()
        app.state.stream = old_stream
        with patch("aylo_app.app.close_input_stream") as close_stream, patch(
            "aylo_app.app.open_input_stream", return_value=replacement
        ) as open_stream:
            self.assertTrue(app._refresh_microphone_stream("test"))
        close_stream.assert_called_once_with(old_stream)
        open_stream.assert_called_once_with(app.state, app.log_error)
        self.assertIs(app.state.stream, replacement)

    def test_quiet_voice_retries_with_adaptive_sensitivity(self):
        app = self.make_app()
        app.state.settings.silence_rms_threshold = 0.0008
        with patch(
            "aylo_app.app.transcribe_frames",
            side_effect=[AudioQualityError("quiet", "silence"), "quiet speech recognized"],
        ) as transcribe:
            result = app._transcribe([object()])
        self.assertEqual(result, "quiet speech recognized")
        self.assertEqual(transcribe.call_count, 2)
        self.assertEqual(transcribe.call_args_list[0].kwargs["silence_rms_threshold"], 0.0008)
        self.assertEqual(transcribe.call_args_list[1].kwargs["silence_rms_threshold"], 0.0002)


if __name__ == "__main__":
    unittest.main()
