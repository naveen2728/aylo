import ctypes
import threading
import time
from ctypes import wintypes

from pynput import keyboard as kb
from pynput import mouse as ms

from .state import STATE_IDLE, STATE_RECORDING


ESCAPE_DOUBLE_TAP_SECONDS = 0.7
RIGHT_SHIFT_HOLD_DELAY_SECONDS = 0.08
MOUSE_BACK_BUTTON = getattr(ms.Button, "x1", None)
MOUSE_FORWARD_BUTTON = getattr(ms.Button, "x2", None)
MOUSE_MIC_BUTTONS = tuple(
    button
    for button in (MOUSE_BACK_BUTTON, MOUSE_FORWARD_BUTTON)
    if button is not None
)


WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_QUIT = 0x0012
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
XBUTTON1 = 1
XBUTTON2 = 2
VK_BROWSER_BACK = 0xA6
VK_BROWSER_FORWARD = 0xA7
VK_CONTROL = 0x11
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_SPACE = 0x20
VK_RSHIFT = 0xA1


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


LowLevelMouseProc = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
LowLevelKeyboardProc = ctypes.WINFUNCTYPE(wintypes.LPARAM, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MouseSideButtonHook:
    def __init__(self, on_button, log_error=None, on_hotkey=None):
        self.on_button = on_button
        self.log_error = log_error or (lambda _message, _exc=None: None)
        self.on_hotkey = on_hotkey
        self.thread = None
        self.thread_id = None
        self.hook = None
        self.keyboard_hook = None
        self.callback = None
        self.keyboard_callback = None
        self.ready = threading.Event()

    def start(self):
        if self.thread is not None:
            return
        self.ready.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread_id:
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
        self.thread = None
        self.thread_id = None
        self.ready.clear()

    def _run(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD
            kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
            kernel32.GetModuleHandleW.restype = wintypes.HMODULE
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelMouseProc, wintypes.HINSTANCE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HHOOK
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.HINSTANCE, wintypes.DWORD]
            user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = wintypes.LPARAM
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
            user32.UnhookWindowsHookEx.restype = wintypes.BOOL
            user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user32.PostThreadMessageW.restype = wintypes.BOOL
            user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = wintypes.BOOL

            self.thread_id = kernel32.GetCurrentThreadId()
            self.callback = LowLevelMouseProc(self._callback)
            self.keyboard_callback = LowLevelKeyboardProc(self._keyboard_callback)
            module = kernel32.GetModuleHandleW(None)
            self.hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self.callback, module, 0)
            self.keyboard_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.keyboard_callback, module, 0)
            if not self.hook and not self.keyboard_hook:
                error_code = kernel32.GetLastError()
                self.log_error("Mouse side button hooks failed", ctypes.WinError(error_code))
                return
            self.log_error(
                f"Mouse side button hooks active: raw_mouse={bool(self.hook)}, browser_keys={bool(self.keyboard_hook)}"
            )
            self.ready.set()
            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self.log_error("Mouse side button hook crashed", exc)
        finally:
            if self.hook:
                user32.UnhookWindowsHookEx(self.hook)
            if self.keyboard_hook:
                user32.UnhookWindowsHookEx(self.keyboard_hook)
            self.hook = None
            self.keyboard_hook = None
            self.ready.clear()

    def _callback(self, n_code, w_param, l_param):
        if n_code == HC_ACTION and w_param in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            event = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            button_id = (event.mouseData >> 16) & 0xFFFF
            button = MOUSE_BACK_BUTTON if button_id == XBUTTON1 else MOUSE_FORWARD_BUTTON if button_id == XBUTTON2 else None
            if button and self.on_button(button, w_param == WM_XBUTTONDOWN, "mouse"):
                return 1
        return ctypes.windll.user32.CallNextHookEx(self.hook, n_code, w_param, l_param)

    def _keyboard_callback(self, n_code, w_param, l_param):
        if n_code == HC_ACTION and w_param in (WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP):
            event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            pressed = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
            button = None
            if event.vkCode == VK_BROWSER_BACK:
                button = MOUSE_BACK_BUTTON
            elif event.vkCode == VK_BROWSER_FORWARD:
                button = MOUSE_FORWARD_BUTTON
            if button and self.on_button(button, pressed, "keyboard"):
                return 1
            if self.on_hotkey:
                self.on_hotkey(event.vkCode, pressed)
        return ctypes.windll.user32.CallNextHookEx(self.keyboard_hook, n_code, w_param, l_param)


class HotkeyListener:
    def __init__(
        self,
        state,
        start_recording,
        stop_and_process,
        cancel_recording,
        close_app,
        start_voice_chat=None,
        stop_voice_chat=None,
        is_voice_chat_active=None,
        log_error=None,
    ):
        self.state = state
        self.start_recording = start_recording
        self.stop_and_process = stop_and_process
        self.cancel_recording = cancel_recording
        self.close_app = close_app
        self.start_voice_chat = start_voice_chat
        self.stop_voice_chat = stop_voice_chat
        self.is_voice_chat_active = is_voice_chat_active
        self.log_error = log_error or (lambda _message, _exc=None: None)
        self.ctrl_pressed = False
        self.space_pressed = False
        self.right_shift_pressed = False
        self.right_shift_blocked = False
        self.right_shift_pending = None
        self.escape_pressed = False
        self.last_escape_press = 0.0
        self.chord_down = False
        self.chord_input_mode = None
        self.chord_recording_mode = None
        self.mouse_buttons_pressed = set()
        self.mouse_button_sources = {}
        self.mouse_recording_mode = None
        self.mouse_listener = None
        self.listener = kb.Listener(on_press=self.on_press, on_release=self.on_release)

    def start(self):
        self.listener.start()
        self.refresh_mouse_listener()
        self.log_error("Hotkey listener active: Right Shift=dictation, Ctrl+Space=AI command")

    def stop(self):
        self.listener.stop()
        self._stop_mouse_listener()
        self._cancel_pending_right_shift()

    def refresh_mouse_listener(self):
        enabled = bool(getattr(self.state.settings, "mouse_side_button_mic", False))
        if enabled and self.mouse_listener is None:
            self.mouse_listener = MouseSideButtonHook(
                self.handle_mouse_button_event,
                self.log_error,
                self.handle_native_hotkey_event,
            )
            self.mouse_listener.start()
        elif not enabled:
            self._stop_mouse_listener()

    def _stop_mouse_listener(self):
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
            self.mouse_listener = None
        self.mouse_buttons_pressed.clear()
        self.mouse_button_sources.clear()
        self.mouse_recording_mode = None

    def on_press(self, key):
        if self.state.is_pasting:
            return
        if key in (kb.Key.ctrl_l, kb.Key.ctrl_r, kb.Key.ctrl):
            self._block_right_shift_modifier()
            self.ctrl_pressed = True
        elif key == kb.Key.space:
            self._block_right_shift_modifier()
            self.space_pressed = True
        elif key == kb.Key.shift_r:
            if not self.right_shift_pressed:
                self.right_shift_blocked = False
            self.right_shift_pressed = True
            self._schedule_right_shift_dictation()
            return
        elif key == kb.Key.backspace:
            self._cancel_pending_right_shift()
            self._reset_chord()
            self.cancel_recording()
            return
        elif key == kb.Key.esc:
            self._cancel_pending_right_shift()
            if self.escape_pressed:
                return
            self.escape_pressed = True
            now = time.monotonic()
            if now - self.last_escape_press <= ESCAPE_DOUBLE_TAP_SECONDS:
                self.last_escape_press = 0.0
                self.close_app()
            else:
                self.last_escape_press = now
            return
        else:
            self._block_right_shift_modifier()
            return

        mode = self._active_chord_mode()
        self._start_chord_if_ready(mode)

    def _start_chord_if_ready(self, mode):
        if mode is not None and not self.chord_down:
            self.log_error(f"Hotkey chord pressed: {mode}")
            self._on_chord_press(mode)

    def _schedule_right_shift_dictation(self):
        if self.chord_down or self.right_shift_pending is not None:
            return
        timer = threading.Timer(RIGHT_SHIFT_HOLD_DELAY_SECONDS, self._start_right_shift_dictation)
        timer.daemon = True
        self.right_shift_pending = timer
        timer.start()

    def _cancel_pending_right_shift(self):
        if self.right_shift_pending is not None:
            self.right_shift_pending.cancel()
            self.right_shift_pending = None

    def _block_right_shift_modifier(self):
        if self.right_shift_pressed:
            self.right_shift_blocked = True
            self._cancel_pending_right_shift()
            # If the user starts a normal shortcut after briefly holding Right
            # Shift, discard that recording rather than transcribing or pasting
            # anything from it.
            if self.chord_down and self.chord_input_mode == "dictation":
                self._reset_chord()
                self.cancel_recording(silent=True)

    def _start_right_shift_dictation(self):
        self.right_shift_pending = None
        if self.state.is_pasting or not self.right_shift_pressed or self.chord_down:
            return
        self.log_error("Hotkey chord pressed: dictation")
        self._on_chord_press("dictation")

    def handle_native_hotkey_event(self, vk_code, pressed):
        """Fallback for keyboards where pynput does not receive global key events."""
        if self.state.is_pasting:
            return

        is_ctrl = vk_code in (VK_CONTROL, VK_LCONTROL, VK_RCONTROL)
        if not is_ctrl and vk_code not in (VK_SPACE, VK_RSHIFT):
            if pressed:
                self._block_right_shift_modifier()
            return

        if is_ctrl:
            self._block_right_shift_modifier()
            self.ctrl_pressed = pressed
        elif vk_code == VK_SPACE:
            self._block_right_shift_modifier()
            self.space_pressed = pressed
        elif vk_code == VK_RSHIFT:
            if pressed and not self.right_shift_pressed:
                self.right_shift_blocked = False
            self.right_shift_pressed = pressed
            if pressed:
                self._schedule_right_shift_dictation()
            else:
                self._cancel_pending_right_shift()
                self.right_shift_blocked = False
                if self.chord_down and self._active_chord_mode() != self.chord_input_mode:
                    self._on_chord_release()
            return

        if pressed:
            mode = self._active_chord_mode()
            self._start_chord_if_ready(mode)
        elif self.chord_down and self._active_chord_mode() != self.chord_input_mode:
            self._on_chord_release()

    def _active_chord_mode(self):
        if self.ctrl_pressed and self.space_pressed:
            return "command"
        if self.right_shift_pressed and not self.right_shift_blocked:
            return "dictation"
        return None

    def _on_chord_press(self, mode):
        self.chord_down = True
        self.chord_input_mode = mode
        with self.state.lock:
            recording_state = self.state.recording_state

        if recording_state == STATE_RECORDING and self.chord_recording_mode is not None:
            self.chord_recording_mode = None
            self.stop_and_process()
        elif recording_state == STATE_IDLE:
            self.chord_recording_mode = mode
            self.start_recording(mode=mode)

    def _reset_chord(self):
        self._cancel_pending_right_shift()
        self.chord_down = False
        self.chord_input_mode = None
        self.chord_recording_mode = None

    def on_release(self, key):
        if key in (kb.Key.ctrl_l, kb.Key.ctrl_r, kb.Key.ctrl):
            self.ctrl_pressed = False
        elif key == kb.Key.space:
            self.space_pressed = False
        elif key == kb.Key.shift_r:
            self.right_shift_pressed = False
            self._cancel_pending_right_shift()
            self.right_shift_blocked = False
        elif key == kb.Key.esc:
            self.escape_pressed = False

        if self.state.is_pasting:
            self.chord_down = False
            return
        if self.chord_down and self._active_chord_mode() != self.chord_input_mode:
            self._on_chord_release()

    def _on_chord_release(self):
        self.chord_down = False
        self.chord_input_mode = None
        with self.state.lock:
            owns_recording = (
                self.state.recording_state == STATE_RECORDING
                and self.chord_recording_mode is not None
                and self.state.recording_mode == self.chord_recording_mode
            )
        if owns_recording:
            self.log_error(f"Hotkey chord released: {self.chord_recording_mode}")
            self.chord_recording_mode = None
            self.stop_and_process()

    def on_click(self, _x, _y, button, pressed):
        self.handle_mouse_button_event(button, pressed)

    def handle_mouse_button_event(self, button, pressed, source="direct"):
        if button not in MOUSE_MIC_BUTTONS:
            return False
        if self.state.is_pasting or not self.state.settings.mouse_side_button_mic:
            return False
        if pressed:
            sources = self.mouse_button_sources.setdefault(button, set())
            already_pressed = bool(sources)
            sources.add(source)
            self.mouse_buttons_pressed.add(button)
            if not already_pressed:
                self._on_mouse_mic_press(button, self._mouse_button_mode(button))
        else:
            sources = self.mouse_button_sources.get(button)
            if sources:
                sources.discard(source)
                if sources:
                    return True
                self.mouse_button_sources.pop(button, None)
            self._on_mouse_mic_release(button)
        return True

    def _mouse_button_name(self, button):
        if button == MOUSE_BACK_BUTTON:
            return "back"
        if button == MOUSE_FORWARD_BUTTON:
            return "forward"
        return str(button)

    def _mouse_button_mode(self, button):
        if button == MOUSE_FORWARD_BUTTON:
            return "command"
        return "dictation"

    def _on_mouse_mic_press(self, button, mode):
        with self.state.lock:
            can_start = self.state.recording_state == STATE_IDLE
        if not can_start:
            return
        self._reset_chord()
        self.mouse_recording_mode = mode
        self.start_recording(mode=mode)

    def _on_mouse_mic_release(self, button):
        if self.state.is_pasting:
            return
        self.mouse_buttons_pressed.discard(button)
        with self.state.lock:
            is_mouse_recording = (
                self.state.recording_state == STATE_RECORDING
                and self.state.recording_mode == self.mouse_recording_mode
                and self.mouse_recording_mode is not None
            )
        if is_mouse_recording and not self.mouse_buttons_pressed:
            self.mouse_recording_mode = None
            self.stop_and_process()
