import base64
import json
import queue
import threading


CONVERSATION_MODEL = "gpt-realtime"
CONVERSATION_URL = f"wss://api.openai.com/v1/realtime?model={CONVERSATION_MODEL}"
SAMPLE_RATE = 24000
BLOCK_SIZE = 1200


class ConversationAgentError(RuntimeError):
    pass


class ConversationAgent:
    """An isolated realtime voice session with transcript callbacks."""

    def __init__(self, api_key, log_error, on_event=None):
        self.api_key = api_key
        self.log_error = log_error
        self.on_event = on_event or (lambda _kind, _payload=None: None)
        self.ws = None
        self.input_stream = None
        self.output_stream = None
        self.output_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.muted = threading.Event()
        self.thread = None

    def start(self):
        if not self.api_key:
            raise ConversationAgentError("OpenAI Realtime API key is missing.")
        try:
            import websocket
        except ImportError as exc:
            raise ConversationAgentError("Install websocket-client, then restart VoiceFlow.") from exc

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
        self.ws = None

    def set_muted(self, muted):
        if muted:
            self.muted.set()
        else:
            self.muted.clear()
        self.on_event("muted", bool(muted))

    def _run(self, websocket):
        self.ws = websocket.WebSocketApp(
            CONVERSATION_URL,
            header=[
                f"Authorization: Bearer {self.api_key}",
                "OpenAI-Safety-Identifier: voiceflow-conversation-user",
            ],
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever()

    def _on_open(self, _ws):
        self._send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "output_modalities": ["audio"],
                    "instructions": (
                        "You are VoiceFlow AI, a helpful conversational voice assistant. "
                        "Respond naturally, warmly, and concisely. Remember context from this "
                        "conversation. Ask a brief follow-up when the user's request is unclear."
                    ),
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                            "noise_reduction": {"type": "near_field"},
                            "transcription": {"model": "gpt-4o-mini-transcribe"},
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,
                                "prefix_padding_ms": 300,
                                "silence_duration_ms": 500,
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
        try:
            self._open_streams()
            self.on_event("status", "Listening")
        except Exception as exc:
            self.log_error("Conversation audio device failed", exc)
            self.on_event("error", "Could not open the microphone or speaker.")
            self.stop()

    def _on_message(self, _ws, message):
        try:
            event = json.loads(message)
        except (TypeError, json.JSONDecodeError):
            return

        event_type = event.get("type", "")
        if event_type == "response.output_audio.delta":
            try:
                self.output_queue.put(base64.b64decode(event.get("delta", "")))
            except Exception as exc:
                self.log_error("Conversation audio decode failed", exc)
        elif event_type == "input_audio_buffer.speech_started":
            self._clear_output_audio()
            self._send({"type": "response.cancel"})
            self.on_event("speech_started", None)
            self.on_event("status", "Listening")
        elif event_type == "input_audio_buffer.speech_stopped":
            self.on_event("status", "Thinking")
        elif event_type == "conversation.item.input_audio_transcription.delta":
            self.on_event("transcript", {"role": "user", "text": event.get("delta", ""), "final": False})
        elif event_type == "conversation.item.input_audio_transcription.completed":
            self.on_event("transcript", {"role": "user", "text": event.get("transcript", ""), "final": True})
        elif event_type in ("response.output_audio_transcript.delta", "response.output_text.delta"):
            self.on_event("transcript", {"role": "assistant", "text": event.get("delta", ""), "final": False})
            self.on_event("status", "Speaking")
        elif event_type in ("response.output_audio_transcript.done", "response.output_text.done"):
            text = event.get("transcript") or event.get("text") or ""
            self.on_event("transcript", {"role": "assistant", "text": text, "final": True})
            self.on_event("status", "Listening")
        elif event_type == "response.done":
            self.on_event("status", "Listening")
        elif event_type == "error":
            message = event.get("error", {}).get("message") or "Realtime conversation error."
            if "no active response" not in message.lower():
                self.log_error("Realtime conversation error", RuntimeError(message))
                self.on_event("error", message)

    def _on_error(self, _ws, error):
        if not self.stop_event.is_set():
            self.log_error("Conversation websocket failed", error)
            self.on_event("error", "Conversation connection failed.")

    def _on_close(self, _ws, _status_code, _message):
        self._close_streams()
        self.on_event("closed", None)

    def _open_streams(self):
        import numpy as np
        import sounddevice as sd

        def input_callback(indata, _frames, _time_info, _status):
            if self.stop_event.is_set() or self.muted.is_set() or not self.ws:
                return
            audio = (indata[:, 0].clip(-1.0, 1.0) * 32767).astype("<i2").tobytes()
            encoded = base64.b64encode(audio).decode("ascii")
            self._send({"type": "input_audio_buffer.append", "audio": encoded})

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
            if data[needed:]:
                self.output_queue.put(bytes(data[needed:]))

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
        for name in ("input_stream", "output_stream"):
            stream = getattr(self, name, None)
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
                setattr(self, name, None)
        self._clear_output_audio()

    def _clear_output_audio(self):
        while True:
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                return

    def _send(self, event):
        try:
            if self.ws:
                self.ws.send(json.dumps(event))
        except Exception as exc:
            if not self.stop_event.is_set():
                self.log_error("Conversation event send failed", exc)
