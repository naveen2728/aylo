import unittest

import numpy as np

from voiceflow_app.transcription import AudioQualityError, transcribe_frames


class FakeModel:
    def __init__(self):
        self.audio = None
        self.options = None

    def transcribe(self, audio, **options):
        self.audio = audio
        self.options = options
        segment = type("Segment", (), {"text": " hello world "})
        return [segment()], None


class MissingVadModel(FakeModel):
    def transcribe(self, audio, **options):
        if options.get("vad_filter"):
            raise RuntimeError("silero_vad_v6.onnx failed: NO_SUCHFILE")
        return super().transcribe(audio, **options)


class EmptyVadModel(FakeModel):
    def transcribe(self, audio, **options):
        if options.get("vad_filter"):
            return [], None
        return super().transcribe(audio, **options)


class EmptyModel(FakeModel):
    def transcribe(self, audio, **options):
        return [], None


class TranscriptionTests(unittest.TestCase):
    def test_rejects_empty_recording(self):
        with self.assertRaisesRegex(AudioQualityError, "No audio captured"):
            transcribe_frames(FakeModel(), [], 16000)

    def test_rejects_short_recording(self):
        frames = [np.ones((100, 1), dtype=np.float32)]
        with self.assertRaisesRegex(AudioQualityError, "too short"):
            transcribe_frames(FakeModel(), frames, 16000)

    def test_rejects_quiet_recording(self):
        frames = [np.zeros((8000, 1), dtype=np.float32)]
        with self.assertRaisesRegex(AudioQualityError, "No microphone signal"):
            transcribe_frames(FakeModel(), frames, 16000)

    def test_rejects_low_level_noise_before_transcription(self):
        frames = [np.full((8000, 1), 0.0001, dtype=np.float32)]
        with self.assertRaisesRegex(AudioQualityError, "No clear voice"):
            transcribe_frames(FakeModel(), frames, 16000)

    def test_transcribes_audible_recording(self):
        model = FakeModel()
        frames = [np.full((8000, 1), 0.1, dtype=np.float32)]
        self.assertEqual(transcribe_frames(model, frames, 16000), "hello world")
        self.assertEqual(model.options["beam_size"], 5)
        self.assertTrue(model.options["vad_filter"])

    def test_resamples_native_microphone_audio_for_whisper(self):
        model = FakeModel()
        frames = [np.full((24000, 1), 0.1, dtype=np.float32)]
        self.assertEqual(transcribe_frames(model, frames, 48000), "hello world")
        self.assertAlmostEqual(len(model.audio) / 16000, 0.5, places=2)

    def test_retries_without_vad_when_packaged_asset_is_missing(self):
        model = MissingVadModel()
        frames = [np.full((8000, 1), 0.1, dtype=np.float32)]

        self.assertEqual(transcribe_frames(model, frames, 16000), "hello world")
        self.assertFalse(model.options["vad_filter"])

    def test_retries_without_vad_when_voice_filter_returns_empty(self):
        model = EmptyVadModel()
        frames = [np.full((8000, 1), 0.1, dtype=np.float32)]

        self.assertEqual(transcribe_frames(model, frames, 16000), "hello world")
        self.assertFalse(model.options["vad_filter"])

    def test_reports_when_both_voice_detection_passes_are_empty(self):
        frames = [np.full((8000, 1), 0.1, dtype=np.float32)]

        with self.assertRaisesRegex(AudioQualityError, "Speech was not recognized"):
            transcribe_frames(EmptyModel(), frames, 16000)

    def test_fallback_uses_a_more_thorough_decoder_pass(self):
        model = EmptyVadModel()
        frames = [np.full((8000, 1), 0.1, dtype=np.float32)]

        self.assertEqual(transcribe_frames(model, frames, 16000), "hello world")
        self.assertFalse(model.options["vad_filter"])
        self.assertEqual(model.options["beam_size"], 5)

    def test_marks_silent_microphone_as_no_signal(self):
        frames = [np.zeros((8000, 1), dtype=np.float32)]

        with self.assertRaises(AudioQualityError) as context:
            transcribe_frames(FakeModel(), frames, 16000)
        self.assertEqual(context.exception.reason, "no_signal")

    def test_transcribes_quiet_realtek_level_recording(self):
        frames = [np.full((8000, 1), 0.00001, dtype=np.float32)]
        self.assertEqual(
            transcribe_frames(FakeModel(), frames, 16000, silence_rms_threshold=0.000001),
            "hello world",
        )

    def test_transcribes_extremely_quiet_nonzero_recording(self):
        frames = [np.full((8000, 1), 0.00000001, dtype=np.float32)]
        self.assertEqual(
            transcribe_frames(FakeModel(), frames, 16000, silence_rms_threshold=0.000000001),
            "hello world",
        )


if __name__ == "__main__":
    unittest.main()
