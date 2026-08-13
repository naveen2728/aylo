from collections import deque
import math
import os
import time

import sounddevice as sd

from .state import STATE_RECORDING


def list_input_devices():
    devices = [{"id": None, "label": "Default microphone"}]
    for index, device in enumerate(sd.query_devices()):
        if device.get("max_input_channels", 0) > 0:
            devices.append({"id": index, "label": f"{index}: {device['name']}"})
    return devices


def resolve_input_device(device):
    if device is not None:
        return device
    wasapi_device = _wasapi_default_input_device()
    if wasapi_device is not None:
        return wasapi_device
    default_device = sd.default.device
    try:
        return default_device[0]
    except (IndexError, TypeError):
        pass
    return device


def _wasapi_default_input_device():
    if os.name != "nt":
        return None
    try:
        for hostapi in sd.query_hostapis():
            if hostapi.get("name") == "Windows WASAPI":
                device = hostapi.get("default_input_device")
                return device if isinstance(device, int) and device >= 0 else None
    except Exception:
        pass
    return None


def resolve_input_samplerate(device, preferred_samplerate):
    try:
        sd.check_input_settings(
            device=device,
            samplerate=preferred_samplerate,
            channels=1,
            dtype="float32",
        )
        return preferred_samplerate
    except Exception:
        device_info = sd.query_devices(device)
        native_samplerate = int(round(device_info["default_samplerate"]))
        sd.check_input_settings(
            device=device,
            samplerate=native_samplerate,
            channels=1,
            dtype="float32",
        )
        return native_samplerate


def open_input_stream(state, log_error=None):
    def audio_callback(indata, frames, time_info, status):
        if status:
            state.last_audio_warning = str(status)
        chunk = indata.copy()
        state.last_audio_callback_at = time.monotonic()
        state.last_audio_rms = float(math.sqrt(float((chunk * chunk).mean()))) if chunk.size else 0.0
        with state.lock:
            if state.recording_state == STATE_RECORDING:
                state.audio_frames.append(chunk)
            else:
                state.pre_buffer.append(chunk)

    def create_stream(device):
        input_samplerate = resolve_input_samplerate(device, state.samplerate)
        blocksize = max(320, int(round(input_samplerate * 0.02)))
        stream = sd.InputStream(
            device=device,
            samplerate=input_samplerate,
            channels=1,
            dtype="float32",
            latency="low",
            blocksize=blocksize,
            callback=audio_callback,
        )
        stream.start()
        return stream, input_samplerate, blocksize

    try:
        device = resolve_input_device(state.mic_device)
        try:
            stream, input_samplerate, blocksize = create_stream(device)
        except Exception as primary_exc:
            # Windows can invalidate a WASAPI endpoint after sleep, a Bluetooth
            # change, or a driver reset. When the user chose the default mic,
            # retry the Windows default endpoint (typically MME) before giving up.
            fallback_device = None
            if state.mic_device is None:
                try:
                    fallback_device = sd.default.device[0]
                except (IndexError, TypeError):
                    pass
            if fallback_device is None or fallback_device == device:
                raise primary_exc
            if log_error:
                log_error(
                    f"WASAPI microphone device {device} failed; retrying default device {fallback_device}",
                    primary_exc,
                )
            stream, input_samplerate, blocksize = create_stream(fallback_device)
        state.input_samplerate = input_samplerate
        state.input_blocksize = blocksize
        pre_buffer_blocks = math.ceil(input_samplerate * state.settings.pre_buffer_seconds / blocksize) + 2
        with state.lock:
            state.pre_buffer = deque(state.pre_buffer, maxlen=pre_buffer_blocks)
        return stream
    except Exception as exc:
        device = "default" if state.mic_device is None else repr(state.mic_device)
        raise RuntimeError(f"Could not open microphone device {device}: {exc}") from exc


def close_input_stream(stream):
    if stream:
        stream.stop()
        stream.close()
