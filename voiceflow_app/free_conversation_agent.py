import threading
import time


class FreeConversationAgent:
    """Turn-based conversation using local speech recognition and Groq."""

    def __init__(self, record_turn, transcribe, generate_reply, speak, log_error, on_event=None):
        self.record_turn = record_turn
        self.transcribe = transcribe
        self.generate_reply = generate_reply
        self.speak = speak
        self.log_error = log_error
        self.on_event = on_event or (lambda _kind, _payload=None: None)
        self.stop_event = threading.Event()
        self.muted = threading.Event()
        self.messages = []
        self.thread = None

    def start(self):
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def set_muted(self, muted):
        if muted:
            self.muted.set()
        else:
            self.muted.clear()
        self.on_event("muted", bool(muted))

    def _run(self):
        self.on_event("status", "Listening · Free mode")
        try:
            while not self.stop_event.is_set():
                if self.muted.is_set():
                    time.sleep(0.1)
                    continue
                frames = self.record_turn(self.stop_event, self.muted)
                if self.stop_event.is_set():
                    break
                if not frames:
                    time.sleep(0.1)
                    continue

                try:
                    self.on_event("status", "Transcribing")
                    user_text = self.transcribe(frames)
                except Exception as exc:
                    if exc.__class__.__name__ != "AudioQualityError":
                        self.log_error("Free conversation transcription failed", exc)
                    self.on_event("status", "Listening · Free mode")
                    continue
                if not user_text:
                    self.on_event("status", "Listening · Free mode")
                    continue

                self.on_event("transcript", {"role": "user", "text": user_text, "final": True})
                self.messages.append({"role": "user", "content": user_text})
                self.on_event("status", "Thinking")
                try:
                    reply = self.generate_reply(self.messages[-20:])
                except Exception as exc:
                    self.log_error("Free conversation reply failed", exc)
                    self.on_event("error", str(exc))
                    self.on_event("status", "Listening · Free mode")
                    continue
                if not reply:
                    self.on_event("status", "Listening · Free mode")
                    continue

                self.messages.append({"role": "assistant", "content": reply})
                self.on_event("transcript", {"role": "assistant", "text": reply, "final": True})
                self.on_event("status", "Speaking · Free mode")
                try:
                    self.speak(reply)
                except Exception as exc:
                    self.log_error("Free conversation speech failed", exc)
                    self.on_event("error", str(exc))
                self.on_event("status", "Listening · Free mode")
        except Exception as exc:
            self.log_error("Free conversation loop failed", exc)
            self.on_event("error", "Free conversation stopped unexpectedly.")
        finally:
            self.on_event("closed", None)
