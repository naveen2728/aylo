import ctypes
import os
import sys
import threading
import time
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog

from . import ai_client
from .audio import close_input_stream, list_input_devices, open_input_stream
from .clipboard_utils import ClipboardContentError, validate_clipboard_content
from .config import (
    ERROR_LOG,
    HISTORY_FILE,
    appdata_dir,
    load_api_key,
    load_image_api_key,
    load_openai_realtime_api_key,
    load_settings,
    save_api_key,
    save_image_api_key,
    save_openai_realtime_api_key,
    save_settings,
)
from .conversation_agent import ConversationAgent, ConversationAgentError
from .conversation_window import ConversationWindow
from .free_conversation_agent import FreeConversationAgent
from .context import get_active_window_title
from .gmail_assistant import answer_gmail_question, generate_gmail_reply, is_gmail_question, is_open_gmail_command, search_gmail
from .gmail_connector import connect_gmail, create_gmail_draft, disconnect_gmail, gmail_status, send_gmail_message, sender_email, sync_gmail_knowledge
from .hotkeys import HotkeyListener
from .image_generation import ImageGenerationError, generate_image, image_prompt_from_request, is_image_generation_request
from .history import HistoryStore, history_label
from .intent import build_clipboard_prompt, build_standalone_prompt, should_use_clipboard
from .logging_utils import log_error
from .overlay import Overlay, SplashScreen, prompt_for_api_key_if_needed
from .prompts import get_prompt_for_window
from .realtime_voice import RealtimeVoiceAgent, RealtimeVoiceError
from .rewrite_actions import REWRITE_ACTIONS, build_rewrite_prompt
from .settings_window import DiagnosticsWindow, OnboardingWindow, SettingsWindow
from .state import RuntimeState, STATE_IDLE, STATE_PROCESSING, STATE_RECORDING
from .startup import is_startup_enabled, set_startup_enabled
from .subscription import checkout_url, open_checkout
from .speech import SpeechError, speak_text
from .transcription import AudioQualityError, load_model, transcribe_frames
from .web_shortcuts import detect_open_shortcut


VOICE_CHAT_TURN_SECONDS = 4.0
VOICE_CHAT_POLL_SECONDS = 0.1
MINIMUM_CAPTURE_SECONDS = 0.9


def enable_dpi_awareness():
    """Use physical-pixel window geometry on high-DPI displays."""
    try:
        context = ctypes.c_void_p(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(context):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


class AyloApp:
    def __init__(self):
        self.state = RuntimeState(load_settings())
        self.overlay = None
        self.hotkeys = None
        self.mutex = None
        self.startup_error = None
        self.history = HistoryStore(HISTORY_FILE)
        self.voice_chat_active = False
        self.voice_chat_stop_event = threading.Event()
        self.realtime_voice_agent = None
        self.conversation_agent = None
        self.conversation_window = None
        self.microphone_refresh_lock = threading.Lock()

    def run(self):
        enable_dpi_awareness()
        self._acquire_single_instance()
        load_api_key()
        load_image_api_key()
        if self.state.settings.ai_features_enabled:
            prompt_for_api_key_if_needed(self._verify_and_save_initial_api_key)
        self._load_services()
        self.overlay = Overlay(
            self.state,
            self.open_settings,
            self.change_api_key,
            self.change_image_api_key,
            self.change_openai_realtime_api_key,
            self.open_diagnostics,
            self.reconnect_ai,
            self.open_onboarding,
            self.open_subscription,
            self.open_log,
            self.request_close,
            self.list_history,
            self.copy_history,
            REWRITE_ACTIONS,
            self.rewrite_clipboard,
            self.custom_rewrite,
            self.is_startup_enabled,
            self.toggle_startup,
            self.clear_history,
            self.connect_gmail,
            self.sync_gmail,
            self.disconnect_gmail,
            self.show_gmail_status,
            self.request_gmail_reply,
            self.create_gmail_draft,
            self.send_gmail_reply,
            self.open_ai_panel,
            self.send_ai_chat,
            self.capture_screen_context,
            self.ask_screen_context,
            self.start_voice_chat,
            self.stop_voice_chat,
            self.is_voice_chat_active,
            self.open_conversation,
        )
        if not self.state.settings.first_run_complete:
            self.overlay.root.after(700, self.open_onboarding)
        self.hotkeys = HotkeyListener(
            self.state,
            self.start_recording,
            self.stop_and_process,
            self.cancel_recording,
            self.request_close,
            self.request_start_voice_chat,
            self.request_stop_voice_chat,
            self.is_voice_chat_active,
            self.log_error,
        )
        self.hotkeys.start()
        self.overlay.run()

    def _verify_and_save_initial_api_key(self, key):
        if not key.startswith("gsk_"):
            raise ValueError("This does not look like a Groq API key. Copy a key beginning with gsk_.")
        try:
            client = ai_client.connect(api_key=key)
        except Exception as exc:
            self.log_error("First-run Groq connection failed", exc)
            raise ValueError(ai_client.friendly_generation_error(exc)) from exc
        save_api_key(key)
        self.state.client = client
        self.state.ai_cleanup = True

    def _acquire_single_instance(self):
        self.mutex = ctypes.windll.kernel32.CreateMutexW(None, False, r"Local\Aylo_SingleInstance")
        last_error = ctypes.windll.kernel32.GetLastError()
        if not self.mutex:
            raise RuntimeError("Could not create Aylo single-instance lock.")
        if last_error == 183:
            ctypes.windll.user32.MessageBoxW(0, "Aylo is already running.", "Aylo", 0x30)
            raise SystemExit(1)

    def _load_services(self):
        splash = SplashScreen()
        load_thread = threading.Thread(target=self._startup_load, args=(splash,), daemon=True)
        load_thread.start()
        splash.win.mainloop()
        load_thread.join()
        if self.startup_error:
            raise RuntimeError(self.startup_error)

    def _startup_load(self, splash):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            splash.set_status("Loading speech model...")
            self.state.model = load_model(splash.set_status, self.log_error)

            if os.environ.get("GROQ_API_KEY") and self.state.client is None:
                splash.set_status("Connecting to Groq...")
                try:
                    self.state.client = ai_client.connect()
                    self.state.ai_cleanup = True
                except Exception as exc:
                    self.log_error("Groq init failed", exc)
                    self.state.client = None
                    self.state.ai_cleanup = False

            splash.set_status("Opening microphone...")
            self.state.stream = open_input_stream(self.state, self.log_error)
        except Exception as exc:
            self.log_error("Startup failed", exc)
            self.startup_error = str(exc)
            ctypes.windll.user32.MessageBoxW(0, str(exc), "Aylo", 0x10)
        finally:
            splash.win.after(0, splash.close)

    def log_error(self, message, exc=None):
        log_error(ERROR_LOG, message, exc)

    def start_recording(self, mode="dictation"):
        with self.state.lock:
            if self.state.recording_state != STATE_IDLE:
                return
        if not self._ensure_microphone_stream_live():
            self.show_toast("Microphone connection failed. Check Settings and try again.")
            return
        with self.state.lock:
            if self.state.recording_state != STATE_IDLE:
                return
            self.state.recording_state = STATE_RECORDING
            self.state.audio_frames = list(self.state.pre_buffer)
            self.state.recording_prebuffer_frames = len(self.state.audio_frames)
            self.state.recording_started_at = time.monotonic()
            self.state.recording_mode = mode
            if mode == "command":
                try:
                    import pyperclip
                    self.state.clipboard_snapshot = pyperclip.paste()
                except Exception as exc:
                    self.log_error("Clipboard capture failed", exc)
                    self.state.clipboard_snapshot = None
        self.state.max_record_timer = threading.Timer(self.state.settings.max_record_seconds, self.emergency_stop)
        self.state.max_record_timer.daemon = True
        self.state.max_record_timer.start()
        self.log_error(f"Recording started: mode={mode}, input_rate={self.state.input_samplerate}")
        self.set_orb("recording")

    def emergency_stop(self):
        with self.state.lock:
            if self.state.recording_state != STATE_RECORDING:
                return
        self.stop_and_process()

    def cancel_recording(self, silent=False):
        with self.state.lock:
            if self.state.recording_state != STATE_RECORDING:
                return
            self.state.recording_state = STATE_IDLE
            self.state.audio_frames = []
            self.state.recording_started_at = 0.0
            self.state.recording_prebuffer_frames = 0
            if self.state.max_record_timer is not None:
                self.state.max_record_timer.cancel()
                self.state.max_record_timer = None
            if self.state.minimum_record_timer is not None:
                self.state.minimum_record_timer.cancel()
                self.state.minimum_record_timer = None
        self.set_orb("idle")
        if not silent:
            self.show_toast("Recording cancelled.")

    def stop_and_process(self):
        with self.state.lock:
            if self.state.recording_state != STATE_RECORDING:
                return
            recording_started_at = self.state.recording_started_at
            held_seconds = max(0.0, time.monotonic() - recording_started_at) if recording_started_at else 0.0
            if recording_started_at and held_seconds < MINIMUM_CAPTURE_SECONDS:
                if self.state.minimum_record_timer is None:
                    remaining = MINIMUM_CAPTURE_SECONDS - held_seconds
                    timer = threading.Timer(remaining, self.stop_and_process)
                    timer.daemon = True
                    self.state.minimum_record_timer = timer
                    timer.start()
                    self.log_error(
                        f"Recording release deferred for short phrase: captured={held_seconds:.2f}, "
                        f"minimum={MINIMUM_CAPTURE_SECONDS:.2f}"
                    )
                return
            self.state.recording_state = STATE_PROCESSING
            frames = self.state.audio_frames.copy()
            self.state.audio_frames = []
            prebuffer_frames = self.state.recording_prebuffer_frames
            self.state.recording_started_at = 0.0
            self.state.recording_prebuffer_frames = 0
            self.state.minimum_record_timer = None
            if self.state.max_record_timer is not None:
                self.state.max_record_timer.cancel()
                self.state.max_record_timer = None
        held_seconds = max(0.0, time.monotonic() - recording_started_at) if recording_started_at else 0.0
        self.log_error(
            f"Recording stopped: mode={self.state.recording_mode}, frames={len(frames)}, "
            f"prebuffer={prebuffer_frames}, held_seconds={held_seconds:.2f}"
        )
        if self._recording_stream_stalled(len(frames), prebuffer_frames, held_seconds):
            self.log_error(
                f"Microphone stream stalled during recording: frames={len(frames)}, "
                f"prebuffer={prebuffer_frames}, held_seconds={held_seconds:.2f}"
            )
            recovered = self._refresh_microphone_stream("recording stream stalled")
            if recovered:
                self.show_toast("Microphone reconnected. Hold Right Shift and speak again.")
            else:
                self.show_toast("Microphone stopped responding. Choose a microphone in Settings.")
            self._set_idle()
            return
        if not frames:
            self.show_toast("No audio captured. Check your microphone and try again.")
            self._set_idle()
            return
        # Keep the orb visibly active while local transcription or AI work is
        # running. This transitions directly from the speaking animation to
        # the thinking animation instead of briefly dropping back to idle.
        self.set_orb("thinking")
        if self.state.recording_mode == "command":
            threading.Thread(target=self._process_command, args=(frames,), daemon=True).start()
        elif self.state.recording_mode == "voice_chat":
            threading.Thread(target=self._process_voice_chat, args=(frames,), daemon=True).start()
        else:
            title = get_active_window_title(self.log_error)
            prompt, _ = get_prompt_for_window(title)
            threading.Thread(target=self._process_dictation, args=(frames, prompt), daemon=True).start()

    def _process_dictation(self, frames, prompt):
        try:
            text = self._transcribe(frames)
            if not text:
                return
            shortcut_url = detect_open_shortcut(text)
            if shortcut_url:
                self.open_web_shortcut(shortcut_url)
                return
            # Dictation is intentionally local-only. AI is reserved for the
            # dedicated command shortcut so spoken text is never unexpectedly
            # rewritten or sent to a provider.
            self._record_history(text, mode="dictation")
            self._paste_text_preserving_clipboard(text, release_keys=("shift",))
        except AudioQualityError as exc:
            self.show_toast(str(exc))
        except Exception as exc:
            self.log_error("Dictation failed", exc)
        finally:
            self._set_idle()

    def _process_command(self, frames):
        try:
            if not self.state.settings.ai_features_enabled:
                self.show_toast("AI Features are off. Enable them in Settings.")
                return
            user_text = self._transcribe(frames)
            if not user_text:
                return
            shortcut_url = detect_open_shortcut(user_text)
            if shortcut_url:
                self.open_web_shortcut(shortcut_url)
                return
            if is_open_gmail_command(user_text):
                self.open_gmail()
                return
            if is_gmail_question(user_text):
                self._process_gmail_question(user_text)
                return
            used_clipboard = should_use_clipboard(user_text)
            if used_clipboard:
                selected_code = self.state.clipboard_snapshot
                try:
                    validate_clipboard_content(selected_code, min_characters=5)
                except ClipboardContentError as exc:
                    self.show_toast(str(exc))
                    return
                prompt = build_clipboard_prompt(user_text, selected_code)
            else:
                prompt = build_standalone_prompt(user_text)
            try:
                client = self._ensure_ai_client()
            except Exception as exc:
                self.log_error("Groq reconnect failed", exc)
                self.show_toast(ai_client.friendly_generation_error(exc))
                return
            if client is None:
                self.show_toast("No API key. Set it from the context menu.")
                return

            self.set_orb("thinking")
            try:
                generated = ai_client.generate(client, prompt, self.log_error)
            except ai_client.GenerationError as exc:
                self.show_toast(str(exc))
                return
            if not generated:
                self.show_toast("No response from AI. Try again.")
                return
            self.set_orb("typing")
            time.sleep(0.2)
            self._record_history(generated, mode="command", used_clipboard=used_clipboard, request=user_text)
            self._paste_text_preserving_clipboard(generated)
            self.set_orb("done")
            time.sleep(0.3)
        except AudioQualityError as exc:
            self.show_toast(str(exc))
        except Exception as exc:
            self.log_error("Command failed", exc)
            self.show_toast("Command failed. Check error log.")
        finally:
            self._set_idle()

    def _process_voice_chat(self, frames):
        try:
            user_text = self._transcribe(frames)
            if not user_text:
                return
            self._answer_voice_chat_text(user_text)
        except AudioQualityError as exc:
            self.show_toast(str(exc))
        except Exception as exc:
            self.log_error("Voice chat failed", exc)
            self.show_toast("Voice chat failed. Check error log.")
        finally:
            self._set_idle()

    def start_voice_chat(self):
        if not self.state.settings.ai_features_enabled:
            self.show_toast("AI Features are off. Enable them in Settings.")
            return
        self.log_error("Realtime voice chat start requested")
        if self.voice_chat_active:
            self.show_toast("Voice chat is already running.")
            return
        with self.state.lock:
            if self.state.recording_state != STATE_IDLE:
                self.show_toast("Finish the current recording first.")
                return

        api_key = load_openai_realtime_api_key()
        if not api_key:
            self.show_toast("Add an OpenAI Realtime API key first.", duration=4000)
            self.change_openai_realtime_api_key()
            api_key = load_openai_realtime_api_key()
            if not api_key:
                return

        try:
            self.realtime_voice_agent = RealtimeVoiceAgent(api_key, self.log_error, self._realtime_voice_status)
            self.realtime_voice_agent.start()
        except RealtimeVoiceError as exc:
            self.realtime_voice_agent = None
            self.show_toast(str(exc), duration=5000)
            return

        self.voice_chat_active = True
        self.set_orb("recording")
        self.show_toast("Realtime voice chat started. Speak anytime to interrupt.", duration=4000)

    def request_start_voice_chat(self):
        self.state.ui_queue.put(("call_ui", self.start_voice_chat))

    def stop_voice_chat(self):
        self.log_error("Realtime voice chat stop requested")
        if not self.voice_chat_active:
            self.show_toast("Voice chat is not running.")
            return
        if self.realtime_voice_agent:
            self.realtime_voice_agent.stop()
            self.realtime_voice_agent = None
        self.voice_chat_active = False
        self.set_orb("idle")
        self.show_toast("Realtime voice chat stopped.")

    def request_stop_voice_chat(self):
        self.state.ui_queue.put(("call_ui", self.stop_voice_chat))

    def is_voice_chat_active(self):
        return self.voice_chat_active

    def open_conversation(self):
        if self.voice_chat_active:
            self.show_toast("Stop the legacy voice chat before opening Conversation.")
            return
        if self.conversation_window is None:
            self.conversation_window = ConversationWindow(
                self.overlay.root,
                self._start_conversation_session,
                self._stop_conversation_session,
                self._set_conversation_muted,
            )
        self.conversation_window.open()

    def _start_conversation_session(self, on_event):
        if self.conversation_agent is not None:
            return
        api_key = load_openai_realtime_api_key()
        if api_key:
            self.conversation_agent = ConversationAgent(api_key, self.log_error, on_event)
        else:
            client = self._ensure_ai_client()
            if client is None:
                raise ConversationAgentError("Add your Groq API key from the orb menu first.")
            self.conversation_agent = FreeConversationAgent(
                self._record_free_conversation_turn,
                self._transcribe,
                lambda messages: ai_client.chat(client, messages, self.log_error),
                speak_text,
                self.log_error,
                on_event,
            )
        try:
            self.conversation_agent.start()
        except Exception:
            self.conversation_agent = None
            raise

    def _stop_conversation_session(self):
        if self.conversation_agent:
            self.conversation_agent.stop()
            self.conversation_agent = None
        with self.state.lock:
            if self.state.recording_mode == "free_conversation":
                self.state.recording_state = STATE_IDLE
                self.state.audio_frames = []
        self.set_orb("idle")

    def _set_conversation_muted(self, muted):
        if self.conversation_agent:
            self.conversation_agent.set_muted(muted)

    def _record_free_conversation_turn(self, stop_event, muted_event, seconds=VOICE_CHAT_TURN_SECONDS):
        with self.state.lock:
            if self.state.recording_state != STATE_IDLE:
                return []
            self.state.recording_state = STATE_RECORDING
            self.state.recording_mode = "free_conversation"
            self.state.audio_frames = []
        self.set_orb("recording")
        deadline = time.monotonic() + seconds
        while not stop_event.is_set() and not muted_event.is_set() and time.monotonic() < deadline:
            time.sleep(VOICE_CHAT_POLL_SECONDS)
        with self.state.lock:
            frames = self.state.audio_frames.copy()
            self.state.audio_frames = []
            if self.state.recording_mode == "free_conversation":
                self.state.recording_state = STATE_IDLE
        self.set_orb("idle")
        if stop_event.is_set() or muted_event.is_set():
            return []
        return frames

    def _realtime_voice_status(self, message):
        if "disconnected" in message.lower() or "failed" in message.lower():
            self.voice_chat_active = False
            self.realtime_voice_agent = None
            self.set_orb("idle")
        self.show_toast(message, duration=3000)

    def _voice_chat_loop(self):
        try:
            while not self.voice_chat_stop_event.is_set():
                frames = self._record_voice_chat_turn()
                if self.voice_chat_stop_event.is_set():
                    break
                if not frames:
                    time.sleep(VOICE_CHAT_POLL_SECONDS)
                    continue
                try:
                    try:
                        user_text = self._transcribe(frames)
                    except AudioQualityError:
                        continue
                    if not user_text:
                        continue
                    self._answer_voice_chat_text(user_text)
                finally:
                    self._finish_voice_chat_turn()
        except Exception as exc:
            self.log_error("Voice chat loop failed", exc)
            self.show_toast("Voice chat failed. Check error log.")
        finally:
            self.voice_chat_active = False
            self.voice_chat_stop_event.clear()
            with self.state.lock:
                if self.state.recording_mode == "voice_chat":
                    self.state.recording_state = STATE_IDLE
                    self.state.audio_frames = []
            self.set_orb("idle")
            self.show_toast("Voice chat stopped.")

    def _record_voice_chat_turn(self, seconds=VOICE_CHAT_TURN_SECONDS):
        with self.state.lock:
            if self.state.recording_state != STATE_IDLE:
                return []
            self.state.recording_state = STATE_RECORDING
            self.state.recording_mode = "voice_chat"
            self.state.audio_frames = []
        self.set_orb("recording")
        deadline = time.monotonic() + seconds
        while not self.voice_chat_stop_event.is_set() and time.monotonic() < deadline:
            time.sleep(VOICE_CHAT_POLL_SECONDS)
        with self.state.lock:
            frames = self.state.audio_frames.copy()
            self.state.audio_frames = []
            if self.state.recording_mode == "voice_chat":
                self.state.recording_state = STATE_PROCESSING
        self.set_orb("idle")
        if self.voice_chat_stop_event.is_set():
            return []
        return frames

    def _finish_voice_chat_turn(self):
        with self.state.lock:
            if self.state.recording_mode == "voice_chat":
                self.state.recording_state = STATE_IDLE
                self.state.audio_frames = []
        self.set_orb("idle")

    def _answer_voice_chat_text(self, user_text):
        try:
            client = self._ensure_ai_client()
        except Exception as exc:
            self.log_error("Groq reconnect failed", exc)
            message = ai_client.friendly_generation_error(exc)
            self.show_toast(message)
            self._speak_ai_reply(message)
            return
        if client is None:
            message = "AI is not connected. Update your API key or check your internet connection."
            self.show_toast(message)
            self._speak_ai_reply(message)
            return

        self.set_orb("thinking")
        try:
            response = ai_client.chat(client, [{"role": "user", "content": user_text}], self.log_error)
        except ai_client.GenerationError as exc:
            self.show_toast(str(exc))
            self._speak_ai_reply(str(exc))
            return
        if not response:
            message = "No response from AI. Try again."
            self.show_toast(message)
            self._speak_ai_reply(message)
            return
        self._record_history(response, mode="voice-chat", request=user_text)
        self.set_orb("typing")
        self._speak_ai_reply(response)
        self.set_orb("done")
        time.sleep(0.3)

    def _speak_ai_reply(self, text):
        try:
            speak_text(text)
        except SpeechError as exc:
            self.log_error("Speech output failed", exc)
            self.show_toast(str(exc))

    def _process_gmail_question(self, user_text):
        self.set_orb("thinking")
        try:
            results = search_gmail(user_text)
        except Exception as exc:
            self.log_error("Gmail question failed", exc)
            self.show_toast(str(exc))
            return
        if not results:
            self.show_toast("No Gmail answer found. Try syncing Gmail first.")
            return
        self._record_history(f"Opened {len(results)} Gmail results.", mode="gmail", request=user_text)
        if self.overlay:
            self.overlay.show_gmail_results(user_text, "", results)
        self.set_orb("done")
        time.sleep(0.3)

    def _paste_text_preserving_clipboard(self, text, release_keys=()):
        import pyautogui
        import pyperclip

        previous_clipboard = pyperclip.paste()
        pyperclip.copy(text)
        try:
            time.sleep(0.3)
            for key in release_keys:
                try:
                    pyautogui.keyUp(key)
                except Exception:
                    pass
            time.sleep(0.1)
            self.state.is_pasting = True
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
            self.log_error(f"Paste completed: characters={len(text)}")
        finally:
            self.state.is_pasting = False
            try:
                pyperclip.copy(previous_clipboard)
            except Exception as exc:
                self.log_error("Clipboard restore failed", exc)

    def _set_idle(self):
        with self.state.lock:
            self.state.recording_state = STATE_IDLE
            self.state.recording_started_at = 0.0
            self.state.recording_prebuffer_frames = 0
        self.set_orb("idle")

    def _transcribe(self, frames):
        started = time.perf_counter()
        try:
            try:
                text = transcribe_frames(
                    self.state.model,
                    frames,
                    self.state.input_samplerate,
                    min_record_seconds=self.state.settings.min_record_seconds,
                    silence_rms_threshold=self.state.settings.silence_rms_threshold,
                )
            except AudioQualityError as exc:
                adaptive_threshold = 0.0002
                if exc.reason != "silence" or self.state.settings.silence_rms_threshold <= adaptive_threshold:
                    raise
                self.log_error(
                    f"Retrying quiet recording with adaptive sensitivity: "
                    f"configured={self.state.settings.silence_rms_threshold:.6f}, adaptive={adaptive_threshold:.6f}"
                )
                text = transcribe_frames(
                    self.state.model,
                    frames,
                    self.state.input_samplerate,
                    min_record_seconds=self.state.settings.min_record_seconds,
                    silence_rms_threshold=adaptive_threshold,
                )
        except AudioQualityError as exc:
            callback_age = (
                max(0.0, time.monotonic() - self.state.last_audio_callback_at)
                if self.state.last_audio_callback_at
                else -1.0
            )
            self.log_error(
                f"Transcription rejected: reason={exc.reason}, frames={len(frames)}, "
                f"callback_age={callback_age:.2f}, last_rms={self.state.last_audio_rms:.6f}, "
                f"audio_rms={exc.rms if exc.rms is not None else -1:.6f}, "
                f"audio_peak={exc.peak if exc.peak is not None else -1:.6f}, "
                f"audio_seconds={exc.seconds if exc.seconds is not None else -1:.2f}"
            )
            if exc.reason == "no_signal":
                self._refresh_microphone_after_no_signal()
            raise
        self.log_error(f"Local transcription completed: seconds={time.perf_counter() - started:.2f}, characters={len(text)}")
        return text

    def _ensure_microphone_stream_live(self, max_callback_age=1.0):
        stream = self.state.stream
        if stream is None:
            # Startup owns the initial open. Tests and early startup can reach
            # this method before a stream exists, so do not open a second one.
            return True
        last_callback = self.state.last_audio_callback_at
        callback_age = time.monotonic() - last_callback if last_callback else float("inf")
        try:
            stream_active = bool(stream.active)
        except Exception:
            stream_active = True
        if stream_active and callback_age <= max_callback_age:
            return True
        self.log_error(
            f"Microphone stream unhealthy before recording: active={stream_active}, "
            f"callback_age={callback_age:.2f}; reconnecting"
        )
        return self._refresh_microphone_stream("stale before recording")

    def _recording_stream_stalled(self, frame_count, prebuffer_frames, held_seconds):
        if held_seconds < 0.6 or self.state.input_samplerate <= 0 or self.state.input_blocksize <= 0:
            return False
        expected_live_frames = held_seconds * self.state.input_samplerate / self.state.input_blocksize
        captured_live_frames = max(0, frame_count - prebuffer_frames)
        return expected_live_frames >= 10 and captured_live_frames < max(3, expected_live_frames * 0.35)

    def _refresh_microphone_stream(self, reason):
        """Recover a stale Windows audio stream after sleep or device changes."""
        if not self.microphone_refresh_lock.acquire(blocking=False):
            return False
        try:
            old_stream = self.state.stream
            self.state.stream = None
            try:
                close_input_stream(old_stream)
            except Exception as exc:
                self.log_error("Previous microphone close failed during refresh", exc)
            try:
                replacement = open_input_stream(self.state, self.log_error)
            except Exception as exc:
                self.log_error(f"Microphone refresh failed: {reason}", exc)
                return False
            self.state.stream = replacement
            self.log_error(f"Microphone stream refreshed: {reason}")
            return True
        finally:
            self.microphone_refresh_lock.release()

    def _refresh_microphone_after_no_signal(self):
        return self._refresh_microphone_stream("no microphone signal")

    def set_orb(self, orb_state):
        if self.overlay:
            self.overlay.set_orb(orb_state)

    def show_toast(self, message, duration=2000):
        if self.overlay:
            self.overlay.show_toast(message, duration)

    def change_api_key(self):
        key = simpledialog.askstring("Update Groq API Key", "Paste your key:", show="*", parent=self.overlay.root)
        if not key or not key.strip():
            return
        key = key.strip().strip("\"'")
        if not key.startswith("gsk_"):
            messagebox.showerror(
                "Aylo",
                "This does not look like a Groq API key. Copy a key beginning with gsk_.",
                parent=self.overlay.root,
            )
            return
        try:
            client = ai_client.connect(api_key=key)
            save_api_key(key)
            self.state.client = client
            self.state.ai_cleanup = True
            messagebox.showinfo("Aylo", "Groq API key connected and saved securely.", parent=self.overlay.root)
        except Exception as exc:
            self.state.client = None
            self.state.ai_cleanup = False
            self.log_error("Groq API key update failed", exc)
            messagebox.showerror("Aylo", ai_client.friendly_generation_error(exc), parent=self.overlay.root)

    def change_image_api_key(self):
        key = simpledialog.askstring("Update Image API Key", "Paste your Pollinations API key:", show="*", parent=self.overlay.root)
        if not key or not key.strip():
            return
        try:
            save_image_api_key(key.strip())
            messagebox.showinfo("Aylo", "Image API key updated.", parent=self.overlay.root)
        except Exception as exc:
            self.log_error("Image API key save failed", exc)
            messagebox.showerror("Aylo", f"Failed: {exc}", parent=self.overlay.root)

    def change_openai_realtime_api_key(self):
        key = simpledialog.askstring(
            "Update OpenAI Realtime API Key",
            "Paste your OpenAI API key for realtime voice:",
            show="*",
            parent=self.overlay.root,
        )
        if not key or not key.strip():
            return
        try:
            save_openai_realtime_api_key(key.strip())
            messagebox.showinfo("Aylo", "Realtime voice API key updated.", parent=self.overlay.root)
        except Exception as exc:
            self.log_error("OpenAI Realtime API key save failed", exc)
            messagebox.showerror("Aylo", f"Failed: {exc}", parent=self.overlay.root)

    def reconnect_ai(self):
        try:
            self.set_orb("thinking")
            key = load_api_key()
            if not key:
                return "No Groq API key found. Add one from Change API Key."
            self.state.client = ai_client.connect()
            self.state.ai_cleanup = True
            return "AI connected."
        except Exception as exc:
            self.state.client = None
            self.state.ai_cleanup = False
            self.log_error("Groq reconnect failed", exc)
            return ai_client.friendly_generation_error(exc)
        finally:
            self.set_orb("idle")

    def open_diagnostics(self):
        DiagnosticsWindow(self.overlay.root, self.diagnostics_status, self.reconnect_ai, self.open_log)

    def diagnostics_status(self):
        key = load_api_key()
        last_error = self._last_error_summary()
        return [
            ("Groq key", "Found" if key else "Missing", bool(key)),
            ("AI client", "Connected" if self.state.client else "Disconnected", self.state.client is not None),
            ("Speech model", "Loaded" if self.state.model else "Not loaded", self.state.model is not None),
            ("Microphone", "Open" if self.state.stream else "Not open", self.state.stream is not None),
            ("Hotkeys", "Active" if self.hotkeys else "Not active", self.hotkeys is not None),
            ("Last error", last_error or "None", not bool(last_error)),
        ]

    def _last_error_summary(self):
        if not os.path.exists(ERROR_LOG):
            return ""
        try:
            with open(ERROR_LOG, "r", encoding="utf-8", errors="replace") as handle:
                lines = [line.strip() for line in handle.readlines() if line.strip()]
        except OSError:
            return "Could not read error log."
        for line in reversed(lines):
            if line.startswith("[") or "Error" in line or "failed" in line.lower():
                return line[-160:]
        return ""

    def open_onboarding(self):
        try:
            devices = list_input_devices()
        except Exception as exc:
            self.log_error("Microphone discovery failed", exc)
            devices = [{"id": self.state.settings.mic_device, "label": "Default microphone"}]
        OnboardingWindow(
            self.overlay.root,
            self.state.settings,
            devices,
            self.apply_settings,
            self.save_api_key_from_setup,
            self.reconnect_ai,
            self.finish_onboarding,
        )

    def save_api_key_from_setup(self, key):
        save_api_key(key)
        self.state.client = None
        self.state.ai_cleanup = False

    def finish_onboarding(self):
        self.state.settings.first_run_complete = True
        save_settings(self.state.settings)
        self.show_toast("Aylo setup complete.")

    def open_subscription(self):
        try:
            if open_checkout():
                self.show_toast("Opening Aylo pricing...")
            else:
                messagebox.showinfo(
                    "Aylo Plus",
                    "This open-source build has no checkout page configured.",
                    parent=self.overlay.root,
                )
        except Exception as exc:
            self.log_error("Open subscription page failed", exc)
            messagebox.showinfo(
                "Aylo Plus",
                f"Open this page to upgrade:\n\n{checkout_url()}",
                parent=self.overlay.root,
            )

    def open_settings(self):
        try:
            devices = list_input_devices()
        except Exception as exc:
            self.log_error("Microphone discovery failed", exc)
            messagebox.showerror("Aylo Settings", f"Could not list microphones: {exc}", parent=self.overlay.root)
            return
        SettingsWindow(
            self.overlay.root,
            self.state.settings,
            devices,
            self.apply_settings,
            ai_key_configured=bool(load_api_key()),
            change_api_key_callback=self.change_api_key,
        )

    def apply_settings(
        self,
        mic_device,
        silence_rms_threshold,
        max_record_seconds,
        mouse_side_button_mic=False,
        mouse_forward_action="command",
        ai_features_enabled=False,
    ):
        previous_device = self.state.mic_device
        next_stream = self.state.stream
        if mic_device != previous_device:
            self.state.mic_device = mic_device
            try:
                next_stream = open_input_stream(self.state, self.log_error)
            except Exception:
                self.state.mic_device = previous_device
                raise

        old_stream = self.state.stream
        self.state.stream = next_stream
        self.state.settings.mic_device = mic_device
        self.state.settings.silence_rms_threshold = silence_rms_threshold
        self.state.settings.max_record_seconds = max_record_seconds
        self.state.settings.mouse_side_button_mic = mouse_side_button_mic
        self.state.settings.mouse_forward_action = mouse_forward_action
        self.state.settings.ai_features_enabled = ai_features_enabled
        if not ai_features_enabled:
            self.state.client = None
            self.state.ai_cleanup = False
        save_settings(self.state.settings)
        if self.hotkeys:
            self.hotkeys.refresh_mouse_listener()
        if next_stream is not old_stream:
            try:
                close_input_stream(old_stream)
            except Exception as exc:
                self.log_error("Previous microphone close failed", exc)

    def open_log(self):
        if os.path.exists(ERROR_LOG):
            os.startfile(ERROR_LOG)

    def list_history(self):
        return [
            {"label": history_label(entry), "text": entry.text}
            for entry in self.history.list_entries()
        ]

    def _record_history(self, text, mode, used_clipboard=False, request=""):
        try:
            self.history.add(text, mode=mode, used_clipboard=used_clipboard, request=request)
        except Exception as exc:
            self.log_error("History save failed", exc)

    def copy_history(self, index):
        entries = self.history.list_entries()
        if index < 0 or index >= len(entries):
            return
        try:
            import pyperclip

            pyperclip.copy(entries[index].text)
            self.show_toast("Copied recent result.")
        except Exception as exc:
            self.log_error("History copy failed", exc)
            self.show_toast("Could not copy recent result.")

    def clear_history(self):
        if not messagebox.askyesno("Aylo", "Clear all recent results?", parent=self.overlay.root):
            return
        try:
            self.history.clear()
            self.show_toast("Recent results cleared.")
        except Exception as exc:
            self.log_error("History clear failed", exc)
            self.show_toast("Could not clear recent results.")

    def connect_gmail(self):
        threading.Thread(target=self._connect_gmail, daemon=True).start()

    def _connect_gmail(self):
        try:
            self.set_orb("thinking")
            connect_gmail()
            self.show_toast("Gmail connected.")
        except Exception as exc:
            self.log_error("Gmail connect failed", exc)
            self.show_toast(str(exc), duration=5000)
        finally:
            self.set_orb("idle")

    def sync_gmail(self):
        threading.Thread(target=self._sync_gmail, daemon=True).start()

    def _sync_gmail(self):
        try:
            self.set_orb("thinking")
            count = sync_gmail_knowledge()
            self.show_toast(f"Synced {count} Gmail messages for important mail search.", duration=4000)
        except Exception as exc:
            self.log_error("Gmail sync failed", exc)
            self.show_toast(str(exc), duration=5000)
        finally:
            self.set_orb("idle")

    def disconnect_gmail(self):
        if not messagebox.askyesno("Aylo", "Disconnect Gmail and remove the saved OAuth token?", parent=self.overlay.root):
            return
        try:
            disconnect_gmail()
            self.show_toast("Gmail disconnected.")
        except Exception as exc:
            self.log_error("Gmail disconnect failed", exc)
            self.show_toast("Could not disconnect Gmail.")

    def show_gmail_status(self):
        try:
            message = gmail_status()
        except Exception as exc:
            self.log_error("Gmail status failed", exc)
            message = str(exc)
        messagebox.showinfo("Gmail Assistant", message, parent=self.overlay.root)

    def open_ai_panel(self):
        if self.overlay:
            self.overlay.show_ai_panel()

    def send_ai_chat(self, message, history=None):
        threading.Thread(target=self._send_ai_chat, args=(message, history or []), daemon=True).start()

    def _ensure_ai_client(self):
        if self.state.client is not None:
            return self.state.client
        if not load_api_key():
            return None
        self.state.client = ai_client.connect()
        self.state.ai_cleanup = True
        return self.state.client

    def _send_ai_chat(self, message, history):
        try:
            self.set_orb("thinking")
            if is_image_generation_request(message):
                prompt = image_prompt_from_request(message)
                image_path = generate_image(prompt)
                response = f"Generated image: {prompt}"
                if self.overlay:
                    self.overlay.show_ai_chat_image(image_path, response)
                self._record_history(response, mode="image", request=message)
                return
            if self.state.client is None:
                try:
                    self._ensure_ai_client()
                except Exception as exc:
                    self.log_error("Groq reconnect failed", exc)
                    response = ai_client.friendly_generation_error(exc)
                    if self.overlay:
                        self.overlay.show_ai_chat_reply(response)
                    self._record_history(response, mode="ai-chat", request=message)
                    return
            if self.state.client is None:
                response = "AI is not connected. Update your API key or check your internet connection."
            else:
                messages = history or [{"role": "user", "content": message}]
                response = ai_client.chat(self.state.client, messages, self.log_error)
            if self.overlay:
                self.overlay.show_ai_chat_reply(response)
            self._record_history(response, mode="ai-chat", request=message)
        except ai_client.GenerationError as exc:
            if self.overlay:
                self.overlay.show_ai_chat_reply(str(exc))
        except ImageGenerationError as exc:
            if self.overlay:
                self.overlay.show_ai_chat_reply(str(exc))
        except Exception as exc:
            self.log_error("AI chat failed", exc)
            if self.overlay:
                self.overlay.show_ai_chat_reply("AI chat failed. Check the error log.")
        finally:
            self.set_orb("idle")

    def capture_screen_context(self):
        import pyautogui

        directory = os.path.join(appdata_dir(), "screenshots")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"screen-{int(time.time())}.png")
        windows = self._hide_aylo_windows_for_capture()
        try:
            image = pyautogui.screenshot()
            image.save(path)
        finally:
            self._restore_aylo_windows(windows)
        return path

    def _hide_aylo_windows_for_capture(self):
        if not self.overlay:
            return []
        windows = []
        for name in ("ai_panel", "gmail_panel", "root"):
            window = getattr(self.overlay, name, None)
            if window is None:
                continue
            try:
                if not window.winfo_exists():
                    continue
                state = window.state()
                windows.append((window, state))
                if state != "withdrawn":
                    window.withdraw()
            except Exception:
                continue
        if windows:
            try:
                self.overlay.root.update()
            except Exception:
                pass
            time.sleep(0.2)
        return windows

    def _restore_aylo_windows(self, windows):
        for window, state in windows:
            if state == "withdrawn":
                continue
            try:
                window.deiconify()
                if state == "iconic":
                    window.iconify()
                elif state not in ("normal", "withdrawn"):
                    window.state(state)
            except Exception:
                continue
        if self.overlay:
            try:
                self.overlay.root.update()
                if self.overlay.ai_panel is not None:
                    self.overlay._enforce_ai_panel_size()
            except Exception:
                pass

    def ask_screen_context(self, question, screenshot_path):
        if not screenshot_path:
            return "I could not capture the screen. Try Screenshot first."
        try:
            self.set_orb("thinking")
            try:
                client = self._ensure_ai_client()
            except Exception as exc:
                self.log_error("Groq reconnect failed", exc)
                return ai_client.friendly_generation_error(exc)
            if client is None:
                return "AI is not connected. Update your Groq API key or check your internet connection."
            response = ai_client.read_screen(client, question, screenshot_path, self.log_error)
            self._record_history(response, mode="screen", request=question)
            return response
        except ai_client.GenerationError as exc:
            return str(exc)
        except Exception as exc:
            self.log_error("Ask screen failed", exc)
            return "I could not read the screenshot. Check your internet connection and try again."
        finally:
            self.set_orb("idle")

    def open_gmail(self):
        self.open_web_shortcut("https://mail.google.com/mail/u/0/#inbox")

    def open_web_shortcut(self, url):
        try:
            import webbrowser

            webbrowser.open(url)
            self.show_toast("Opening site.")
        except Exception as exc:
            self.log_error("Open website failed", exc)
            self.show_toast("Could not open site.")

    def request_gmail_reply(self, message_id):
        instruction = simpledialog.askstring(
            "Draft Gmail Reply",
            "What should the reply say?",
            parent=self.overlay.root,
        )
        if not instruction or not instruction.strip():
            return
        threading.Thread(target=self._request_gmail_reply, args=(message_id, instruction.strip()), daemon=True).start()

    def _request_gmail_reply(self, message_id, instruction):
        try:
            self.set_orb("thinking")
            client = self._ensure_ai_client()
            if client is None:
                self.show_toast("No API key. Set it from the context menu.")
                return
            message, draft_body = generate_gmail_reply(instruction, message_id, client, self.log_error)
            if self.overlay:
                self.overlay.show_gmail_draft(message, draft_body, instruction)
            self._record_history(draft_body, mode="gmail-draft", request=instruction)
        except Exception as exc:
            self.log_error("Gmail reply draft failed", exc)
            self.show_toast(str(exc), duration=5000)
        finally:
            self.set_orb("idle")

    def create_gmail_draft(self, message_id, draft_body):
        if not draft_body.strip():
            self.show_toast("Draft is empty.")
            return
        if not messagebox.askyesno("Aylo", "Create this reply as a Gmail draft? It will not be sent.", parent=self.overlay.root):
            return
        threading.Thread(target=self._create_gmail_draft, args=(message_id, draft_body.strip()), daemon=True).start()

    def _create_gmail_draft(self, message_id, draft_body):
        try:
            from .gmail_index import GmailIndex

            message = GmailIndex().get_message(message_id)
            if message is None:
                self.show_toast("Could not find that email. Sync Gmail and try again.")
                return
            self.set_orb("thinking")
            create_gmail_draft(sender_email(message.sender), message.subject, draft_body, thread_id=message.thread_id)
            self.show_toast("Gmail draft created.", duration=3000)
        except Exception as exc:
            self.log_error("Create Gmail draft failed", exc)
            self.show_toast(str(exc), duration=5000)
        finally:
            self.set_orb("idle")

    def send_gmail_reply(self, message_id, draft_body):
        if not draft_body.strip():
            self.show_toast("Reply is empty.")
            return
        threading.Thread(target=self._send_gmail_reply, args=(message_id, draft_body.strip()), daemon=True).start()

    def _send_gmail_reply(self, message_id, draft_body):
        try:
            from .gmail_index import GmailIndex

            message = GmailIndex().get_message(message_id)
            if message is None:
                self.show_toast("Could not find that email. Sync Gmail and try again.")
                return
            self.set_orb("thinking")
            send_gmail_message(sender_email(message.sender), message.subject, draft_body, thread_id=message.thread_id)
            self.show_toast("Gmail reply sent.", duration=3000)
            self._record_history(draft_body, mode="gmail-sent", request=f"Reply to {message.subject}")
        except Exception as exc:
            self.log_error("Send Gmail reply failed", exc)
            self.show_toast(str(exc), duration=5000)
        finally:
            self.set_orb("idle")

    def is_startup_enabled(self):
        try:
            return is_startup_enabled()
        except Exception as exc:
            self.log_error("Startup status check failed", exc)
            return False

    def toggle_startup(self):
        try:
            enabled = not is_startup_enabled()
            set_startup_enabled(enabled)
            self.show_toast("Launch at startup enabled." if enabled else "Launch at startup disabled.")
        except Exception as exc:
            self.log_error("Startup setting failed", exc)
            self.show_toast("Could not update launch-at-startup setting.")

    def custom_rewrite(self):
        instruction = simpledialog.askstring(
            "Custom Clipboard Rewrite",
            "What should Aylo do with the copied content?\n\n"
            "Example: Turn this into meeting notes with action items.",
            parent=self.overlay.root,
        )
        if instruction and instruction.strip():
            self.rewrite_clipboard(instruction.strip())

    def rewrite_clipboard(self, instruction):
        threading.Thread(target=self._rewrite_clipboard, args=(instruction,), daemon=True).start()

    def _rewrite_clipboard(self, instruction):
        try:
            import pyperclip

            clipboard_content = pyperclip.paste()
            try:
                validate_clipboard_content(clipboard_content)
            except ClipboardContentError as exc:
                self.show_toast(str(exc))
                return
            try:
                client = self._ensure_ai_client()
            except Exception as exc:
                self.log_error("Groq reconnect failed", exc)
                self.show_toast(ai_client.friendly_generation_error(exc))
                return
            if client is None:
                self.show_toast("No API key. Set it from the context menu.")
                return
            self.set_orb("thinking")
            prompt = build_rewrite_prompt(instruction, clipboard_content)
            try:
                generated = ai_client.generate(client, prompt, self.log_error)
            except ai_client.GenerationError as exc:
                self.show_toast(str(exc))
                return
            if not generated:
                self.show_toast("No response from AI. Try again.")
                return
            pyperclip.copy(generated)
            self._record_history(generated, mode="rewrite", used_clipboard=True, request=instruction)
            self.set_orb("done")
            self.show_toast("Rewritten text copied.")
        except Exception as exc:
            self.log_error("Clipboard rewrite failed", exc)
            self.show_toast("Clipboard rewrite failed. Check error log.")
        finally:
            time.sleep(0.3)
            self.set_orb("idle")

    def request_close(self):
        if self.overlay:
            self.overlay.root.after(0, self.close)

    def close(self):
        self._stop_conversation_session()
        if self.voice_chat_active:
            self.stop_voice_chat()
        self._set_idle()
        if self.state.max_record_timer is not None:
            self.state.max_record_timer.cancel()
        try:
            close_input_stream(self.state.stream)
        except Exception:
            pass
        if self.hotkeys:
            self.hotkeys.stop()
        if self.mutex:
            ctypes.windll.kernel32.CloseHandle(self.mutex)
            self.mutex = None
        if self.overlay:
            self.overlay.root.destroy()


def main():
    AyloApp().run()
