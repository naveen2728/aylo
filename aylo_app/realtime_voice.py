import base64
import json
import queue
import threading


REALTIME_MODEL = "gpt-realtime"
REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"
SAMPLE_RATE = 24000
BLOCK_SIZE = 1200


class RealtimeVoiceError(RuntimeError):
    pass


class RealtimeVoiceAgent:
    def __init__(self, api_key, log_error, on_status=None):
        self.api_key = api_key
        self.log_error = log_error
        self.on_status = on_status or (lambda _message: None)
        self.ws = None
        self.input_stream = None
        self.output_stream = None
        self.output_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.thread = None

    def start(self):
        if not self.api_key:
            raise RealtimeVoiceError("OpenAI Realtime API key is missing.")
        try:
            import websocket
        except ImportError as exc:
            raise RealtimeVoiceError("Install websocket-client, then restart Aylo.") from exc

        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(websocket,), daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self._close_streams()
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

    def _run(self, websocket):
        headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Safety-Identifier: aylo-local-user",
        ]
        self.ws = websocket.WebSocketApp(
            REALTIME_URL,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever()

    def _on_open(self, ws):
        self.connected_event.set()
        self.on_status("Realtime voice connected.")
        try:
            self._send(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "output_modalities": ["audio"],
                        "instructions": (
                            "You are Aylo AI. Speak naturally and briefly. "
                            "Be warm, practical, and conversational."
                        ),
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                                "noise_reduction": {"type": "near_field"},
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.5,
                                    "prefix_padding_ms": 300,
                                    "silence_duration_ms": 450,
                                    "create_response": True,
                                    "interrupt_response": True,
                                },
                            },
                            "output": {
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                                "voice": "marin",
                                "speed": 1.0,
                            },
                        },
                    },
                }
            )
            self._open_streams()
        except Exception as exc:
            self.on_status("Realtime voice audio device failed.")
            self.log_error("Realtime audio device failed", exc)
            self.stop()

    def _on_message(self, _ws, message):
        try:
            event = json.loads(message)
        except json.JSONDecodeError:
            return
        event_type = event.get("type")
        if event_type == "response.output_audio.delta":
            try:
                self.output_queue.put(base64.b64decode(event.get("delta", "")))
            except Exception as exc:
                self.log_error("Realtime audio decode failed", exc)
        elif event_type == "input_audio_buffer.speech_started":
            self._clear_output_audio()
            self._send({"type": "response.cancel"})
        elif event_type == "error":
            message = event.get("error", {}).get("message") or "Realtime voice error."
            self.on_status(message)
            self.log_error("Realtime voice error", RuntimeError(message))

    def _on_error(self, _ws, error):
        if not self.stop_event.is_set():
            self.on_status("Realtime voice connection failed.")
            self.log_error("Realtime websocket failed", error)

    def _on_close(self, _ws, _status_code, _message):
        self._close_streams()
        if not self.stop_event.is_set():
            self.on_status("Realtime voice disconnected.")

    def _open_streams(self):
        import numpy as np
        import sounddevice as sd

        def input_callback(indata, _frames, _time_info, _status):
            if self.stop_event.is_set() or not self.ws:
                return
            audio = (indata[:, 0].clip(-1.0, 1.0) * 32767).astype("<i2").tobytes()
            self._send({"type": "input_audio_buffer.append", "audio": base64.b64encode(audio).decode("ascii")})

        def output_callback(outdata, frames, _time_info, _status):
            data = bytearray()
            needed = frames * 2
            while len(data) < needed:
                try:
                    data.extend(self.output_queue.get_nowait())
                except queue.Empty:
                    break
            if len(data) < needed:
                data.extend(b"\x00" * (needed - len(data)))
            samples = np.frombuffer(bytes(data[:needed]), dtype="<i2").astype("float32") / 32768.0
            outdata[:, 0] = samples
            leftover = data[needed:]
            if leftover:
                self.output_queue.put(bytes(leftover))

        self.input_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=input_callback,
        )
        self.output_stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
            callback=output_callback,
        )
        self.output_stream.start()
        self.input_stream.start()

    def _close_streams(self):
        for stream_name in ("input_stream", "output_stream"):
            stream = getattr(self, stream_name, None)
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                setattr(self, stream_name, None)
        self._clear_output_audio()

    def _clear_output_audio(self):
        while True:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

    def _send(self, event):
        try:
            if self.ws:
                self.ws.send(json.dumps(event))
        except Exception as exc:
            if not self.stop_event.is_set():
                self.log_error("Realtime event send failed", exc)
