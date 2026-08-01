import os
import math

from .config import model_location


class AudioQualityError(ValueError):
    def __init__(self, message, reason="audio_quality", *, rms=None, peak=None, seconds=None):
        super().__init__(message)
        self.reason = reason
        self.rms = rms
        self.peak = peak
        self.seconds = seconds


def load_model(set_status, log_error):
    from faster_whisper import WhisperModel

    location, local_only = model_location()
    bundled_model = os.path.isfile(os.path.join(location, "model.bin"))
    model_name_or_path = location if bundled_model else "base.en"

    for compute_type in ["int8", "int8_float32", "float32"]:
        try:
            return WhisperModel(
                model_name_or_path,
                device="cpu",
                compute_type=compute_type,
                cpu_threads=min(8, max(1, os.cpu_count() or 1)),
                num_workers=1,
                download_root=None if bundled_model else location,
                local_files_only=local_only,
            )
        except Exception as exc:
            log_error(f"Whisper load failed ({compute_type})", exc)
            if not local_only:
                set_status("Downloading model...")
    raise RuntimeError("Could not load speech model. CPU may be too old.")


def transcribe_frames(model, frames, samplerate, min_record_seconds=0.3, silence_rms_threshold=0.0008):
    import numpy as np

    if not frames:
        raise AudioQualityError("No audio captured. VoiceFlow will refresh the microphone automatically.", "no_signal")
    audio = np.concatenate(frames, axis=0).flatten().astype(np.float32)
    duration_seconds = len(audio) / samplerate
    if duration_seconds < min_record_seconds:
        raise AudioQualityError(
            "Recording was too short. Hold the shortcut while speaking.",
            "too_short",
            seconds=duration_seconds,
        )
    max_value = float(np.max(np.abs(audio)))
    if max_value == 0:
        raise AudioQualityError(
            "No microphone signal detected. VoiceFlow will refresh the microphone; retry once.",
            "no_signal",
            rms=0.0,
            peak=0.0,
            seconds=duration_seconds,
        )
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms < silence_rms_threshold:
        raise AudioQualityError(
            "No clear voice detected. Hold the shortcut and speak normally.",
            "silence",
            rms=rms,
            peak=max_value,
            seconds=duration_seconds,
        )
    if samplerate != 16000:
        from scipy.signal import resample_poly

        divisor = math.gcd(int(samplerate), 16000)
        audio = resample_poly(audio, 16000 // divisor, int(samplerate) // divisor).astype(np.float32)
    audio = audio / max_value
    options = {
        "language": "en",
        # A wider search makes the bundled offline Whisper model more accurate
        # for short commands and varied accents. VoiceFlow records on demand,
        # so the small extra processing time is preferable to a wrong paste.
        "beam_size": 5,
        "condition_on_previous_text": False,
        "without_timestamps": True,
        "vad_filter": True,
        "vad_parameters": {"min_silence_duration_ms": 300, "speech_pad_ms": 200},
    }
    try:
        text = _run_transcription(model, audio, options)
    except Exception as exc:
        message = str(exc).lower()
        if "silero_vad" not in message and not ("no_suchfile" in message and "onnx" in message):
            raise
        text = ""
    if not text:
        options["vad_filter"] = False
        options.pop("vad_parameters", None)
        # VAD can reject short phrases or quiet speech.  Give the decoder a
        # more thorough second pass before asking the user to retry.
        options["beam_size"] = 5
        text = _run_transcription(model, audio, options)
    if not text:
        raise AudioQualityError(
            "Speech was not recognized. Retry once, speak for at least one second, or choose another microphone in Settings.",
            "not_recognized",
            rms=rms,
            peak=max_value,
            seconds=duration_seconds,
        )
    return text


def _run_transcription(model, audio, options):
    segments, _ = model.transcribe(audio, **options)
    return " ".join(segment.text.strip() for segment in segments).strip()
