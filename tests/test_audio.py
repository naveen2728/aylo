import unittest
from unittest.mock import patch

import numpy as np

from voiceflow_app.audio import list_input_devices, open_input_stream, resolve_input_device
from voiceflow_app.config import AppSettings
from voiceflow_app.state import RuntimeState


class AudioTests(unittest.TestCase):
    def test_resolves_default_input_device(self):
        with patch("voiceflow_app.audio._wasapi_default_input_device", return_value=None), patch("voiceflow_app.audio.sd.default.device", [3, 7]):
            self.assertEqual(resolve_input_device(None), 3)
        self.assertEqual(resolve_input_device(5), 5)

    def test_prefers_wasapi_default_input_device(self):
        with patch("voiceflow_app.audio._wasapi_default_input_device", return_value=10):
            self.assertEqual(resolve_input_device(None), 10)

    def test_lists_default_and_input_devices_only(self):
        devices = [
            {"name": "Speakers", "max_input_channels": 0},
            {"name": "USB Mic", "max_input_channels": 1},
        ]
        with patch("voiceflow_app.audio.sd.query_devices", return_value=devices):
            self.assertEqual(
                list_input_devices(),
                [
                    {"id": None, "label": "Default microphone"},
                    {"id": 1, "label": "1: USB Mic"},
                ],
            )

    def test_microphone_failure_identifies_device(self):
        state = RuntimeState(AppSettings(mic_device=4))
        with patch("voiceflow_app.audio.sd.InputStream", side_effect=OSError("device unavailable")):
            with self.assertRaisesRegex(RuntimeError, "microphone device 4"):
                open_input_stream(state)

    def test_stream_uses_low_latency_native_wasapi_rate(self):
        state = RuntimeState(AppSettings())
        stream = unittest.mock.Mock()
        with patch("voiceflow_app.audio._wasapi_default_input_device", return_value=10), patch(
            "voiceflow_app.audio.sd.check_input_settings",
            side_effect=[ValueError("16 kHz unsupported"), None],
        ), patch("voiceflow_app.audio.sd.query_devices", return_value={"default_samplerate": 48000}), patch(
            "voiceflow_app.audio.sd.InputStream", return_value=stream
        ) as input_stream:
            open_input_stream(state)
        kwargs = input_stream.call_args.kwargs
        self.assertEqual(kwargs["device"], 10)
        self.assertEqual(kwargs["samplerate"], 48000)
        self.assertEqual(kwargs["latency"], "low")
        self.assertEqual(kwargs["blocksize"], 960)
        self.assertEqual(state.input_samplerate, 48000)
        stream.start.assert_called_once_with()

    def test_audio_callback_tracks_freshness_and_signal_level(self):
        state = RuntimeState(AppSettings())
        stream = unittest.mock.Mock()
        with patch("voiceflow_app.audio._wasapi_default_input_device", return_value=10), patch(
            "voiceflow_app.audio.sd.check_input_settings"
        ), patch("voiceflow_app.audio.sd.InputStream", return_value=stream) as input_stream, patch(
            "voiceflow_app.audio.time.monotonic", return_value=123.0
        ):
            open_input_stream(state)
            callback = input_stream.call_args.kwargs["callback"]
            callback(np.full((320, 1), 0.25, dtype=np.float32), 320, None, None)
        self.assertEqual(state.last_audio_callback_at, 123.0)
        self.assertAlmostEqual(state.last_audio_rms, 0.25, places=5)
        self.assertEqual(len(state.pre_buffer), 1)


if __name__ == "__main__":
    unittest.main()
