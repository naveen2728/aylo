import ctypes
import io
import math
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.messagebox as messagebox
import tkinter.simpledialog as simpledialog
import webbrowser
from urllib.parse import quote_plus


# Keep the transparent window fixed while leaving a little more breathing room
# around the visible orb artwork on high-DPI displays.
ORB_W, ORB_H, CX, CY, R, FLOOR = 148, 168, 74, 76, 50, 102
AI_PANEL_W = 900
AI_PANEL_H = 780
AI_PANEL_MARGIN = 20
PULSE_PADDING = 8
OUTER_RING_RADIUS = R + PULSE_PADDING
AI_INPUT_FONT_SIZE = 14
AI_REPLY_FONT_SIZE = 16
AI_PENDING_FONT_SIZE = 15
# A fixed logo mark: equal-width/equal-gap columns with exact left-right symmetry.
BLDS = [
    {"dx": -40, "w": 8, "baseH": 20, "phase": 0.0, "speed": 1.9},
    {"dx": -28, "w": 8, "baseH": 32, "phase": 1.3, "speed": 2.4},
    {"dx": -16, "w": 8, "baseH": 44, "phase": 0.5, "speed": 1.6},
    {"dx": -4, "w": 8, "baseH": 56, "phase": 2.0, "speed": 2.1},
    {"dx": 8, "w": 8, "baseH": 44, "phase": 0.2, "speed": 1.4},
    {"dx": 20, "w": 8, "baseH": 32, "phase": 2.5, "speed": 2.6},
    {"dx": 32, "w": 8, "baseH": 20, "phase": 1.0, "speed": 1.7},
]
SHADES = ["#f3f4f6"] * len(BLDS)
MENU_STYLE = {
    "bg": "#171717",
    "fg": "#e5e7eb",
    "activebackground": "#334155",
    "activeforeground": "#ffffff",
    "font": ("Segoe UI", 18),
    "borderwidth": 2,
    "relief": "solid",
}

TK_BASE_SCALING = 96 / 72


def normalize_tk_scaling(window):
    """Keep Tk fonts aligned with physical-pixel geometry under Per-Monitor V2."""
    try:
        window.tk.call("tk", "scaling", TK_BASE_SCALING)
    except Exception:
        pass


def scaled_crop_box(start_x, start_y, end_x, end_y, scale, image_width, image_height, min_size=8):
    if scale <= 0:
        return None
    left = max(0, min(start_x, end_x))
    top = max(0, min(start_y, end_y))
    right = min(image_width * scale, max(start_x, end_x))
    bottom = min(image_height * scale, max(start_y, end_y))
    if right - left < min_size or bottom - top < min_size:
        return None
    return (
        int(left / scale),
        int(top / scale),
        int(right / scale),
        int(bottom / scale),
    )


def screenshot_editor_preview_limits(screen_width, screen_height):
    """Use most of the display for screenshot inspection without covering OS edges."""
    return (
        max(420, min(1280, screen_width - 80)),
        max(300, min(720, screen_height - 240)),
    )


def render_screenshot_annotations(image, annotations, crop_box=None):
    """Return a cropped screenshot with shape and text annotations rendered."""
    from PIL import ImageDraw, ImageFont

    source = image.convert("RGB")
    if crop_box is None:
        crop_box = (0, 0, source.width, source.height)
    left, top, right, bottom = crop_box
    result = source.crop((left, top, right, bottom))
    draw = ImageDraw.Draw(result)

    for annotation in annotations:
        color = annotation.get("color", "#2563eb")
        kind = annotation.get("kind")
        x1 = int(annotation.get("x1", 0) - left)
        y1 = int(annotation.get("y1", 0) - top)
        x2 = int(annotation.get("x2", x1) - left)
        y2 = int(annotation.get("y2", y1) - top)
        width = max(2, int(annotation.get("width", 3)))
        box = (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        if kind == "rectangle":
            draw.rectangle(box, outline=color, width=width)
        elif kind == "ellipse":
            draw.ellipse(box, outline=color, width=width)
        elif kind == "arrow":
            draw.line((x1, y1, x2, y2), fill=color, width=width)
            angle = math.atan2(y2 - y1, x2 - x1)
            head_length = max(10, width * 4)
            wing = head_length * 0.55
            back_x = x2 - head_length * math.cos(angle)
            back_y = y2 - head_length * math.sin(angle)
            left_point = (
                back_x + wing * math.sin(angle),
                back_y - wing * math.cos(angle),
            )
            right_point = (
                back_x - wing * math.sin(angle),
                back_y + wing * math.cos(angle),
            )
            draw.polygon(((x2, y2), left_point, right_point), fill=color)
        elif kind == "text":
            text = str(annotation.get("text", "")).strip()
            if not text:
                continue
            size = max(14, int(annotation.get("font_size", 24)))
            try:
                font = ImageFont.truetype("arial.ttf", size)
            except OSError:
                font = ImageFont.load_default()
            # A light background keeps notes legible on both dark and bright screens.
            text_box = draw.textbbox((x1, y1), text, font=font, stroke_width=1)
            padding = max(4, size // 5)
            background = (
                text_box[0] - padding,
                text_box[1] - padding,
                text_box[2] + padding,
                text_box[3] + padding,
            )
            draw.rounded_rectangle(background, radius=padding, fill="#ffffff")
            draw.text((x1, y1), text, fill=color, font=font, stroke_width=1, stroke_fill=color)
    return result


def copy_image_to_clipboard(image):
    """Copy a Pillow image to the Windows clipboard as bitmap data."""
    import win32clipboard

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "BMP")
    dib = buffer.getvalue()[14:]
    buffer.close()
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
    finally:
        win32clipboard.CloseClipboard()


def looks_like_screen_question(text):
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    direct_phrases = (
        "what is it",
        "what is this",
        "what's this",
        "what's it",
        "explain this",
        "explain it",
        "read this",
        "read it",
        "summarize this",
        "help with this",
        "what am i seeing",
    )
    if normalized in direct_phrases:
        return True
    return any(word in normalized for word in ("screen", "screenshot", "image", "error", "window", "page"))


def format_chat_display_text(text):
    """Turn lightweight Markdown into readable plain text for Tk labels."""
    formatted = (text or "").replace("\r\n", "\n")
    formatted = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", formatted)
    formatted = re.sub(r"(?m)^(\s*)[-*+]\s+", r"\1• ", formatted)
    formatted = re.sub(r"(?m)^(\s*)\d+[.)]\s+", r"\1• ", formatted)
    formatted = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda match: match.group(1) or match.group(2), formatted)
    formatted = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)", lambda match: match.group(1) or match.group(2), formatted)
    formatted = re.sub(r"`([^`\n]+)`", r"\1", formatted)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    return formatted.strip()


def thinking_display_text(label, step):
    base = (label or "Thinking").strip().rstrip(".")
    return f"{base}{'.' * (step % 4)}"


def animated_bar_height(bar, anim_t, state):
    if state == "recording":
        amplitude = 0.42
    elif state in ("thinking", "cleaning"):
        amplitude = 0.16
    else:
        return bar["baseH"]
    wave = math.sin(anim_t * bar["speed"] + bar["phase"]) * bar["baseH"] * amplitude
    return max(4, int(bar["baseH"] + wave))


def pulse_ring_style(state, anim_t):
    styles = {
        "recording": ("#ffffff", 3.0, 3),
        "cleaning": ("#d4d4d4", 2.0, 2),
        "thinking": ("#e5e5e5", 2.5, 2),
        "typing": ("#f5f5f5", 1.5, 2),
        "done": ("#d4d4d4", 1.0, 2),
    }
    if state not in styles:
        return OUTER_RING_RADIUS, "#2a2a2a", 1
    color, pulse_amount, width = styles[state]
    pulse = (math.sin(anim_t * 3.6) + 1.0) * 0.5
    return OUTER_RING_RADIUS + pulse_amount * pulse, color, width


class SplashScreen:
    def __init__(self):
        self.win = tk.Tk()
        normalize_tk_scaling(self.win)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="#111111")
        width, height = 370, 132
        screen_width = self.win.winfo_screenwidth()
        screen_height = self.win.winfo_screenheight()
        self.win.geometry(f"{width}x{height}+{(screen_width-width)//2}+{(screen_height-height)//2}")
        tk.Label(self.win, text="VoiceFlow", bg="#111111", fg="#ffffff", font=("Helvetica", 24, "bold")).pack(pady=(18, 4))
        self.status = tk.Label(self.win, text="Starting...", bg="#111111", fg="#a3a3a3", font=("Helvetica", 14))
        self.status.pack()
        self.timeout_id = self.win.after(30000, self._timeout)
        self.win.update()

    def _timeout(self):
        ctypes.windll.user32.MessageBoxW(0, "Startup timeout. Check error log.", "VoiceFlow", 0x30)
        sys.exit(1)

    def set_status(self, text):
        self.win.after(0, lambda: self.status.config(text=text))

    def close(self):
        if self.timeout_id:
            self.win.after_cancel(self.timeout_id)
        self.win.destroy()


def prompt_for_api_key_if_needed(save_api_key):
    import os

    if os.environ.get("GROQ_API_KEY"):
        return
    window = tk.Tk()
    normalize_tk_scaling(window)
    window.title("Set up VoiceFlow AI")
    window.resizable(False, False)
    window.attributes("-topmost", True)
    window.configure(bg="#111111")
    width, height = 470, 300
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 2
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.minsize(width, height)
    window.maxsize(width, height)

    body = tk.Frame(window, bg="#111111", padx=24, pady=22)
    body.pack(fill="both", expand=True)
    tk.Label(body, text="Enable VoiceFlow AI", bg="#111111", fg="#ffffff", font=("Segoe UI", 17, "bold")).pack(anchor="w")
    tk.Label(
        body,
        text="Optional: add your free Groq API key for Ctrl + Space AI commands. Right Shift dictation stays offline.",
        bg="#111111", fg="#c4c4c4", wraplength=415, justify="left",
    ).pack(anchor="w", pady=(8, 14))
    tk.Label(body, text="Groq API key (starts with gsk_)", bg="#111111", fg="#e5e7eb").pack(anchor="w")
    key_var = tk.StringVar()
    entry = tk.Entry(body, textvariable=key_var, show="*", bg="#202020", fg="#ffffff", insertbackground="#ffffff", relief="flat")
    entry.pack(fill="x", ipady=7, pady=(5, 12))
    status = tk.Label(body, text="You can add or change this later in Settings.", bg="#111111", fg="#9ca3af", anchor="w")
    status.pack(anchor="w")

    def finish(save):
        key = key_var.get().strip().strip("\"'")
        if save and key:
            try:
                save_api_key(key)
            except Exception as exc:
                status.configure(text=str(exc), fg="#fca5a5")
                return
        window.destroy()

    actions = tk.Frame(body, bg="#111111")
    actions.pack(fill="x", side="bottom", pady=(16, 0))
    tk.Button(actions, text="Skip for now", command=lambda: finish(False), bg="#333333", fg="#dddddd", relief="flat", padx=14, pady=7).pack(side="right")
    tk.Button(actions, text="Save API key", command=lambda: finish(True), bg="#2563eb", fg="#ffffff", relief="flat", padx=14, pady=7).pack(side="right", padx=(0, 8))
    entry.focus_set()
    window.mainloop()


class Overlay:
    def __init__(
        self,
        state,
        open_settings,
        change_api_key,
        change_image_api_key,
        change_openai_realtime_api_key,
        open_diagnostics,
        reconnect_ai,
        open_onboarding,
        open_subscription,
        open_log,
        close_app,
        list_history,
        copy_history,
        rewrite_actions,
        rewrite_clipboard,
        custom_rewrite,
        is_startup_enabled,
        toggle_startup,
        clear_history,
        connect_gmail,
        sync_gmail,
        disconnect_gmail,
        show_gmail_status,
        request_gmail_reply,
        create_gmail_draft,
        send_gmail_reply,
        open_ai_panel,
        send_ai_chat,
        capture_screen_context,
        ask_screen_context,
        start_voice_chat,
        stop_voice_chat,
        is_voice_chat_active,
        open_conversation,
    ):
        self.state = state
        self.open_settings = open_settings
        self.change_api_key = change_api_key
        self.change_image_api_key = change_image_api_key
        self.change_openai_realtime_api_key = change_openai_realtime_api_key
        self.open_diagnostics = open_diagnostics
        self.reconnect_ai = reconnect_ai
        self.open_onboarding = open_onboarding
        self.open_subscription = open_subscription
        self.open_log = open_log
        self.close_app = close_app
        self.list_history = list_history
        self.copy_history = copy_history
        self.rewrite_actions = rewrite_actions
        self.rewrite_clipboard = rewrite_clipboard
        self.custom_rewrite = custom_rewrite
        self.is_startup_enabled = is_startup_enabled
        self.toggle_startup = toggle_startup
        self.clear_history = clear_history
        self.connect_gmail = connect_gmail
        self.sync_gmail = sync_gmail
        self.disconnect_gmail = disconnect_gmail
        self.show_gmail_status = show_gmail_status
        self.request_gmail_reply = request_gmail_reply
        self.create_gmail_draft = create_gmail_draft
        self.send_gmail_reply = send_gmail_reply
        self.open_ai_panel = open_ai_panel
        self.send_ai_chat = send_ai_chat
        self.capture_screen_context = capture_screen_context
        self.ask_screen_context = ask_screen_context
        self.start_voice_chat = start_voice_chat
        self.stop_voice_chat = stop_voice_chat
        self.is_voice_chat_active = is_voice_chat_active
        self.open_conversation = open_conversation
        self.gmail_panel = None
        self.gmail_panel_body = None
        self.ai_panel = None
        self.ai_messages_body = None
        self.ai_canvas = None
        self.ai_canvas_window = None
        self.ai_scrollbar = None
        self.ai_messages_spacer = None
        self.ai_layout_pending = False
        self.ai_clamping_size = False
        self.ai_image_refs = []
        self.ai_message_widgets = []
        self.ai_attachment_frame = None
        self.ai_attachment_photo = None
        self.ai_chat_text_widget = None
        self.ai_fixed_size = None
        self.gmail_result_cards = {}
        self.gmail_reply_editors = {}
        self.ai_messages = []
        self.pending_screen_path = None
        self.screen_context_path = None
        self.orb_state = "idle"
        self.anim_t = 0.0
        self.last_anim_time = 0.0
        self.previous_state = None
        self.drag_x = 0
        self.drag_y = 0
        self.orb_size_clamping = False

        self.root = tk.Tk()
        normalize_tk_scaling(self.root)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{ORB_W}x{ORB_H}+1200+50")
        self.root.minsize(ORB_W, ORB_H)
        self.root.maxsize(ORB_W, ORB_H)
        self.root.resizable(False, False)
        self.root.attributes("-transparentcolor", "black")
        self.root.configure(bg="black")
        self.canvas = tk.Canvas(self.root, width=ORB_W, height=ORB_H, highlightthickness=0, bg="black")
        self.canvas.pack_propagate(False)
        self.canvas.pack()
        self._build_canvas()
        self.canvas.bind("<ButtonPress-1>", self._start_move)
        self.canvas.bind("<B1-Motion>", self._do_move)
        self.canvas.bind("<ButtonPress-3>", self._show_context_menu)
        self.root.bind("<Configure>", self._enforce_orb_size, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.root.after(50, self._schedule_ui_updates)
        self.root.after(100, self._animate_loop)

    def run(self):
        self.root.mainloop()

    def set_orb(self, orb_state):
        self.state.ui_queue.put(("set_orb", orb_state))

    def show_toast(self, message, duration=2000):
        self.state.ui_queue.put(("toast", message, duration))

    def _schedule_ui_updates(self):
        try:
            while True:
                command = self.state.ui_queue.get_nowait()
                try:
                    self._handle_ui_command(command)
                except Exception as exc:
                    self._show_toast_impl(f"UI error: {exc}", 4000)
        except queue.Empty:
            pass
        self.root.after(50, self._schedule_ui_updates)

    def _handle_ui_command(self, command):
        if command[0] == "set_orb":
            self.orb_state = command[1]
        elif command[0] == "toast":
            self._show_toast_impl(command[1], command[2])
        elif command[0] == "gmail_results":
            self._show_gmail_results_impl(command[1], command[2], command[3])
        elif command[0] == "gmail_draft":
            self._show_gmail_draft_impl(command[1], command[2], command[3])
        elif command[0] == "ai_panel":
            self._show_ai_panel_impl()
        elif command[0] == "ai_chat_reply":
            self._show_ai_chat_reply_impl(command[1])
        elif command[0] == "ai_chat_image":
            self._show_ai_chat_image_impl(command[1], command[2])
        elif command[0] == "call_ui":
            command[1]()

    def _show_toast_impl(self, message, duration):
        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#1a1a1a")
        tk.Label(toast, text=message, bg="#1a1a1a", fg="#fca5a5", font=("Segoe UI", 10), padx=16, pady=9).pack()
        toast.geometry(f"+{self.root.winfo_x()}+{self.root.winfo_y() + ORB_H - 18}")
        toast.after(duration, toast.destroy)

    def show_gmail_results(self, question, answer, results):
        self.state.ui_queue.put(("gmail_results", question, answer, results))

    def show_gmail_draft(self, message, draft_body, instruction):
        self.state.ui_queue.put(("gmail_draft", message, draft_body, instruction))

    def show_ai_panel(self):
        self.state.ui_queue.put(("ai_panel",))

    def show_ai_chat_reply(self, text):
        self.state.ui_queue.put(("ai_chat_reply", text))

    def show_ai_chat_image(self, path, text):
        self.state.ui_queue.put(("ai_chat_image", path, text))

    def _ensure_gmail_panel(self, title="VoiceFlow AI"):
        if self.gmail_panel and self.gmail_panel.winfo_exists():
            self.gmail_panel.destroy()
        self.gmail_result_cards = {}
        self.gmail_reply_editors = {}
        self.gmail_panel = tk.Toplevel(self.root)
        self.gmail_panel.title(title)
        self.gmail_panel.attributes("-topmost", True)
        self.gmail_panel.configure(bg="#101010")
        width, height = self._panel_size(self.gmail_panel)
        screen_width = self.gmail_panel.winfo_screenwidth()
        screen_height = self.gmail_panel.winfo_screenheight()
        x = max(0, screen_width - width - AI_PANEL_MARGIN)
        y = max(AI_PANEL_MARGIN, (screen_height - height) // 2)
        self.gmail_panel.geometry(f"{width}x{height}+{x}+{y}")
        self.gmail_panel.minsize(width, height)
        self.gmail_panel.maxsize(width, height)
        self.gmail_panel.resizable(False, False)
        header = tk.Frame(self.gmail_panel, bg="#101010", padx=24, pady=18)
        header.pack(fill="x")
        title_block = tk.Frame(header, bg="#101010")
        title_block.pack(side="left")
        tk.Label(title_block, text=title, bg="#101010", fg="#ffffff", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(title_block, text="Conversation", bg="#101010", fg="#8f8f8f", font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 0))
        tk.Button(header, text="Close", command=self.gmail_panel.destroy, bg="#242424", fg="#dddddd", relief="flat", padx=14, pady=8, font=("Segoe UI", 10)).pack(side="right")
        if title == "VoiceFlow AI":
            tk.Button(header, text="Clear", command=self._clear_ai_chat, bg="#242424", fg="#dddddd", relief="flat", padx=14, pady=8, font=("Segoe UI", 10)).pack(side="right", padx=(0, 8))

        canvas = tk.Canvas(self.gmail_panel, bg="#101010", highlightthickness=0)
        scrollbar = tk.Scrollbar(self.gmail_panel, orient="vertical", command=canvas.yview)
        self.gmail_panel_body = tk.Frame(canvas, bg="#101010", padx=24, pady=12)
        self.gmail_panel_body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=self.gmail_panel_body, anchor="nw", width=width - 22)
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(canvas_window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._bind_mousewheel(canvas)
        self._lock_panel_size(self.gmail_panel)
        return self.gmail_panel_body

    def _show_gmail_results_impl(self, question, answer, results):
        body = self._ensure_gmail_panel("VoiceFlow AI")
        self._chat_bubble(body, question, "user")
        if not results:
            self._chat_bubble(body, "I could not find matching Gmail messages. Sync Gmail and ask again.", "assistant")
            return
        self._chat_bubble(body, f"I found {len(results)} relevant email{'s' if len(results) != 1 else ''}.", "assistant")
        self._section_label(body, "Relevant Gmail")
        for result in results:
            card = tk.Frame(body, bg="#101010", padx=4, pady=18)
            card.pack(fill="x", pady=(0, 0))
            top = tk.Frame(card, bg="#101010")
            top.pack(fill="x")
            meta = tk.Frame(top, bg="#101010")
            meta.pack(side="left", fill="x", expand=True)
            buttons = tk.Frame(top, bg="#101010")
            buttons.pack(side="right", anchor="ne")
            self._panel_label(meta, result.get("sender", ""), 14, "#ffffff", bold=True)
            self._panel_label(meta, result.get("subject", "(no subject)"), 17, "#e5e7eb", bold=True)
            tk.Button(buttons, text="Open in Gmail", command=lambda item=result: self._open_gmail_search(item), bg="#242424", fg="#dddddd", relief="flat", padx=18, pady=10, font=("Segoe UI", 12)).pack(anchor="e", pady=(0, 8))
            tk.Button(buttons, text="Reply", command=lambda item=result: self.request_gmail_reply(item["message_id"]), bg="#2563eb", fg="#ffffff", relief="flat", padx=18, pady=10, font=("Segoe UI", 12, "bold")).pack(anchor="e")
            self._panel_label(card, f"{result.get('date', '')}\nReason: {result.get('reason', '')}", 14, "#a3a3a3")
            preview = (result.get("content") or "").strip()
            if preview:
                if len(preview) > 760:
                    preview = preview[:757].rstrip() + "..."
                self._panel_label(card, preview, 14, "#d4d4d4")
            self.gmail_result_cards[result["message_id"]] = card
            separator = tk.Frame(body, bg="#252525", height=1)
            separator.pack(fill="x", pady=(2, 0))

    def _show_gmail_draft_impl(self, message, draft_body, instruction):
        parent = self.gmail_result_cards.get(message.message_id)
        if parent is None or not parent.winfo_exists():
            body = self._ensure_gmail_panel("Gmail Assistant")
            parent = tk.Frame(body, bg="#101010", padx=4, pady=14)
            parent.pack(fill="x", pady=(12, 0))
            self.gmail_result_cards[message.message_id] = parent
            self._panel_label(parent, message.sender, 11, "#ffffff", bold=True)
            self._panel_label(parent, message.subject, 12, "#e5e7eb", bold=True)

        existing = self.gmail_reply_editors.get(message.message_id)
        if existing is not None and existing.winfo_exists():
            existing.destroy()

        reply = tk.Frame(parent, bg="#181818", padx=16, pady=16)
        reply.pack(fill="x", pady=(16, 0))
        self.gmail_reply_editors[message.message_id] = reply
        self._panel_label(reply, f"Reply: {instruction}", 12, "#a3a3a3")
        text = tk.Text(reply, height=12, wrap="word", bg="#0f0f0f", fg="#ffffff", insertbackground="#ffffff", relief="flat", padx=14, pady=14, font=("Segoe UI", 13))
        text.insert("1.0", draft_body)
        text.pack(fill="both", expand=True, pady=(10, 8))
        actions = tk.Frame(reply, bg="#171717")
        actions.pack(fill="x")
        tk.Button(actions, text="Copy", command=lambda: self._copy_text_widget(text), bg="#242424", fg="#dddddd", relief="flat", padx=16, pady=8, font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Open in Gmail", command=lambda: self._open_gmail_search({"subject": message.subject}), bg="#242424", fg="#dddddd", relief="flat", padx=16, pady=8, font=("Segoe UI", 11)).pack(side="left", padx=(0, 8))
        tk.Button(actions, text="Send", command=lambda: self.send_gmail_reply(message.message_id, text.get("1.0", "end").strip()), bg="#991b1b", fg="#ffffff", relief="flat", padx=18, pady=8, font=("Segoe UI", 11, "bold")).pack(side="left")

    def _show_ai_panel_impl(self):
        self._ensure_ai_chat_panel()
        self._present_panel(self.ai_panel)
        self._render_ai_messages()

    def _show_ai_chat_reply_impl(self, text):
        if self.ai_messages and self.ai_messages[-1].get("pending"):
            self.ai_messages[-1].update({"role": "assistant", "text": text})
            self.ai_messages[-1].pop("pending", None)
            self._update_last_ai_message(text)
            return
        self.ai_messages.append({"role": "assistant", "text": text})
        self._append_ai_message(self.ai_messages[-1])
        self._scroll_ai_to_bottom()

    def _show_ai_chat_image_impl(self, path, text):
        if self.ai_messages and self.ai_messages[-1].get("pending"):
            self.ai_messages.pop()
            self._remove_last_ai_message_widget()
        self.ai_messages.append({"role": "assistant", "text": text, "image_path": path, "can_crop": False})
        self._append_ai_message(self.ai_messages[-1])
        self._scroll_ai_to_bottom()

    def _send_ai_chat_from_widget(self, text_widget):
        text = text_widget.get("1.0", "end").strip()
        if not text:
            return
        if self.pending_screen_path:
            screenshot_path = self.pending_screen_path
            self.pending_screen_path = None
            self._render_pending_attachment()
            self._ask_screen_question(text_widget, text, screenshot_path)
            return
        if self.screen_context_path and looks_like_screen_question(text):
            self._ask_screen_question(text_widget, text, self.screen_context_path)
            return
        text_widget.delete("1.0", "end")
        text_widget.configure(height=2)
        self.ai_messages.append({"role": "user", "text": text})
        self.ai_messages.append({"role": "assistant", "text": "Thinking...", "pending": True})
        self._append_ai_message(self.ai_messages[-2])
        self._append_ai_message(self.ai_messages[-1])
        self._scroll_ai_to_bottom()
        history = [
            {"role": message["role"], "content": message["text"]}
            for message in self.ai_messages
            if not message.get("pending") and message["role"] in ("user", "assistant")
        ]
        self.send_ai_chat(text, history)

    def _ensure_ai_chat_panel(self):
        if self.ai_panel and self.ai_panel.winfo_exists():
            return
        self.ai_panel = tk.Toplevel(self.root)
        self.ai_panel.withdraw()
        self.ai_panel.title("VoiceFlow AI")
        self.ai_panel.attributes("-topmost", True)
        self.ai_panel.configure(bg="#101010")
        width, height, x, y = self._panel_geometry(self.ai_panel)
        self.ai_fixed_size = (width, height)
        self.ai_panel.geometry(f"{width}x{height}+{x}+{y}")
        self.ai_panel.minsize(width, height)
        self.ai_panel.maxsize(width, height)
        self.ai_panel.resizable(False, False)
        self.ai_panel.pack_propagate(False)
        self.ai_panel.protocol("WM_DELETE_WINDOW", self._close_ai_panel)
        self.ai_panel.grid_columnconfigure(0, weight=1)
        self.ai_panel.grid_rowconfigure(1, weight=1)
        header = tk.Frame(self.ai_panel, bg="#101010", padx=14, pady=10)
        header.grid(row=0, column=0, sticky="ew")
        title_block = tk.Frame(header, bg="#101010")
        title_block.pack(side="left")
        tk.Label(title_block, text="VoiceFlow AI", bg="#101010", fg="#ffffff", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(title_block, text="Conversation", bg="#101010", fg="#8f8f8f", font=("Segoe UI", 12)).pack(anchor="w", pady=(1, 0))
        tk.Button(header, text="Close", command=self._close_ai_panel, bg="#242424", fg="#dddddd", relief="flat", padx=9, pady=5, font=("Segoe UI", 12)).pack(side="right")
        tk.Button(header, text="Clear", command=self._clear_ai_chat, bg="#242424", fg="#dddddd", relief="flat", padx=9, pady=5, font=("Segoe UI", 12)).pack(side="right", padx=(0, 6))

        content = tk.Frame(self.ai_panel, bg="#101010")
        content.grid(row=1, column=0, sticky="nsew")
        self.ai_canvas = tk.Canvas(content, bg="#101010", highlightthickness=0)
        self.ai_scrollbar = tk.Scrollbar(content, orient="vertical", command=self.ai_canvas.yview)
        self.ai_canvas.configure(yscrollcommand=self.ai_scrollbar.set)
        self.ai_messages_body = tk.Frame(self.ai_canvas, bg="#101010", padx=16, pady=10)
        self.ai_canvas_window = self.ai_canvas.create_window((0, 0), window=self.ai_messages_body, anchor="nw", width=width)
        self.ai_messages_body.bind("<Configure>", lambda event: self._sync_ai_message_layout())
        self.ai_canvas.bind("<Configure>", lambda event: self._resize_ai_canvas_window(event.width))
        self.ai_canvas.pack(side="left", fill="both", expand=True)
        self.ai_scrollbar.pack(side="right", fill="y")
        self.ai_panel.bind("<MouseWheel>", self._scroll_ai_with_wheel, add="+")
        self.ai_panel.bind("<Button-4>", self._scroll_ai_with_wheel, add="+")
        self.ai_panel.bind("<Button-5>", self._scroll_ai_with_wheel, add="+")
        self._chat_input(self.ai_panel, use_grid=True)
        self._render_pending_attachment()

    def _close_ai_panel(self):
        if self.ai_panel and self.ai_panel.winfo_exists():
            self.ai_panel.destroy()
        self.ai_panel = None
        self.ai_messages_body = None
        self.ai_canvas = None
        self.ai_canvas_window = None
        self.ai_scrollbar = None
        self.ai_messages_spacer = None
        self.ai_layout_pending = False
        self.ai_clamping_size = False
        self.ai_attachment_frame = None
        self.ai_attachment_photo = None
        self.ai_chat_text_widget = None
        self.ai_message_widgets = []
        self.ai_fixed_size = None

    def _lock_panel_size(self, panel):
        if panel is None or not panel.winfo_exists():
            return
        fixed_size = self.ai_fixed_size if panel == self.ai_panel else None
        width, height = fixed_size or self._panel_size(panel)
        x = panel.winfo_x()
        y = panel.winfo_y()
        panel.geometry(f"{width}x{height}+{x}+{y}")
        panel.minsize(width, height)
        panel.maxsize(width, height)
        panel.resizable(False, False)

    def _enforce_ai_panel_size(self):
        if self.ai_panel is None or not self.ai_panel.winfo_exists():
            return
        width, height = self.ai_fixed_size or self._panel_size(self.ai_panel)
        x = max(0, self.ai_panel.winfo_x())
        y = max(0, self.ai_panel.winfo_y())
        self.ai_panel.minsize(width, height)
        self.ai_panel.maxsize(width, height)
        self.ai_panel.resizable(False, False)
        self.ai_clamping_size = True
        self.ai_panel.geometry(f"{width}x{height}+{x}+{y}")
        self.ai_panel.after_idle(lambda: setattr(self, "ai_clamping_size", False))

    def _clamp_ai_panel_configure(self, event):
        if self.ai_clamping_size:
            return
        if self.ai_panel is None or event.widget != self.ai_panel:
            return
        width, height = self.ai_fixed_size or self._panel_size(self.ai_panel)
        if event.width != width or event.height != height:
            self.ai_panel.after_idle(self._enforce_ai_panel_size)

    def _present_panel(self, panel):
        if panel is None or not panel.winfo_exists():
            return
        width, height, x, y = self._panel_geometry(panel)
        panel.attributes("-topmost", True)
        panel.geometry(f"{width}x{height}+{x}+{y}")
        panel.deiconify()
        panel.lift()
        try:
            panel.focus_set()
        except Exception:
            pass

    def _render_ai_messages(self):
        if self.ai_messages_body is None:
            return
        self._reset_ai_messages_body()
        self.ai_image_refs = []
        self.ai_message_widgets = []
        if not self.ai_messages:
            self._empty_ai_state(self.ai_messages_body)
        else:
            for message in self.ai_messages:
                self._append_ai_message(message)
        self._sync_ai_message_layout()

    def _append_ai_message(self, message):
        if self.ai_messages_body is None:
            return
        if len(self.ai_message_widgets) == 0:
            self._reset_ai_messages_body()
        widgets = []
        if message.get("image_path"):
            preview = self._screenshot_preview(self.ai_messages_body, message["image_path"], message)
            if preview is not None:
                widgets.append(preview)
        bubble = self._chat_bubble(
            self.ai_messages_body,
            message["text"],
            message["role"],
            pending=bool(message.get("pending")),
        )
        widgets.append(bubble)
        self.ai_message_widgets.append({"widgets": widgets, "label": getattr(bubble, "message_label", None)})
        self._sync_ai_message_layout()
        self._scroll_ai_to_bottom()

    def _reset_ai_messages_body(self):
        if self.ai_messages_body is None:
            return
        for child in self.ai_messages_body.winfo_children():
            child.destroy()
        self.ai_messages_spacer = tk.Frame(self.ai_messages_body, bg="#101010", height=0)
        self.ai_messages_spacer.pack(fill="x")

    def _resize_ai_canvas_window(self, width):
        if self.ai_canvas is None or self.ai_canvas_window is None:
            return
        self.ai_canvas.itemconfigure(self.ai_canvas_window, width=width)
        self._sync_ai_message_layout()

    def _sync_ai_message_layout(self):
        if self.ai_canvas is None or self.ai_messages_body is None:
            return
        if self.ai_messages_spacer is None or not self.ai_messages_spacer.winfo_exists():
            return
        if self.ai_layout_pending:
            return
        self.ai_layout_pending = True

        def apply_layout():
            try:
                if self.ai_canvas is None or self.ai_messages_body is None:
                    return
                if self.ai_messages_spacer is None or not self.ai_messages_spacer.winfo_exists():
                    return
                self.ai_messages_body.update_idletasks()
                canvas_height = max(1, self.ai_canvas.winfo_height())
                content_height = sum(
                    child.winfo_reqheight()
                    for child in self.ai_messages_body.winfo_children()
                    if child is not self.ai_messages_spacer
                )
                spacer_height = max(0, canvas_height - content_height - 18)
                if self.ai_messages_spacer.winfo_reqheight() != spacer_height:
                    self.ai_messages_spacer.configure(height=spacer_height)
                self.ai_canvas.configure(scrollregion=self.ai_canvas.bbox("all"))
            finally:
                self.ai_layout_pending = False

        self.ai_canvas.after_idle(apply_layout)

    def _remove_last_ai_message_widget(self):
        if not self.ai_message_widgets:
            return
        item = self.ai_message_widgets.pop()
        for widget in item.get("widgets", []):
            try:
                widget.destroy()
            except Exception:
                pass

    def _update_last_ai_message(self, text):
        if not self.ai_message_widgets:
            self._render_ai_messages()
            return
        label = self.ai_message_widgets[-1].get("label")
        if label is None or not label.winfo_exists():
            self._render_ai_messages()
            return
        label.thinking = False
        bubble = label.master
        bubble.configure(bg="#1a1a1a", padx=13, pady=9)
        copy_button = getattr(bubble, "copy_button", None)
        if copy_button is not None:
            copy_button.configure(
                command=lambda value=text: self._copy_chat_message(value),
                bg="#1a1a1a",
            )
            copy_button.pack(anchor="e", pady=(0, 2), before=label)
        label.configure(
            text=format_chat_display_text(text),
            bg="#1a1a1a",
            fg="#e5e5e5",
            font=("Segoe UI", AI_REPLY_FONT_SIZE),
        )
        self._sync_ai_message_layout()
        self._scroll_ai_to_bottom()

    def _scroll_ai_to_bottom(self):
        if self.ai_canvas is not None and self.ai_canvas.winfo_exists():
            self.ai_canvas.after_idle(lambda: self.ai_canvas.yview_moveto(1.0) if self.ai_canvas.winfo_exists() else None)

    def _chat_input(self, parent, use_grid=False):
        box = tk.Frame(parent, bg="#151515", padx=12, pady=9)
        if use_grid:
            box.grid(row=2, column=0, sticky="ew")
        else:
            box.pack(fill="x", side="bottom")
        self.ai_attachment_frame = tk.Frame(box, bg="#151515")
        text = tk.Text(box, height=2, wrap="word", bg="#0b0b0b", fg="#ffffff", insertbackground="#ffffff", relief="flat", padx=8, pady=5, font=("Segoe UI", AI_INPUT_FONT_SIZE))
        self.ai_chat_text_widget = text
        text.pack(fill="x", pady=(0, 7))
        text.focus_set()
        text.bind("<Return>", lambda event: self._handle_chat_enter(event, text))
        text.bind("<KP_Enter>", lambda event: self._handle_chat_enter(event, text))
        text.bind("<Shift-Return>", lambda event: self._insert_chat_newline(text))
        text.bind("<Control-Return>", lambda event: self._insert_chat_newline(text))
        actions = tk.Frame(box, bg="#151515")
        actions.pack(fill="x")
        tk.Button(actions, text="Screenshot & Markup", command=self._capture_screen_for_chat, bg="#242424", fg="#dddddd", relief="flat", padx=9, pady=5, font=("Segoe UI", 12)).pack(side="left")
        tk.Button(actions, text="Send", command=lambda: self._send_ai_chat_from_widget(text), bg="#2563eb", fg="#ffffff", relief="flat", padx=16, pady=5, font=("Segoe UI", 12, "bold")).pack(side="right")
        return text

    def _handle_chat_enter(self, event, text_widget):
        if event.state & 0x0001:
            return self._insert_chat_newline(text_widget)
        self._send_ai_chat_from_widget(text_widget)
        return "break"

    def _insert_chat_newline(self, text_widget):
        text_widget.insert("insert", "\n")
        return "break"

    def _queue_ai_layout_refresh(self):
        if self.ai_panel is None or not self.ai_panel.winfo_exists():
            return
        self.ai_panel.after_idle(self._sync_ai_message_layout)

    def _clear_ai_chat(self):
        self.ai_messages = []
        self.pending_screen_path = None
        self.screen_context_path = None
        self._render_pending_attachment()
        self._render_ai_messages()

    def _capture_screen_for_chat(self):
        try:
            path = self.capture_screen_context()
        except Exception as exc:
            self._show_toast_impl(f"Screenshot failed: {exc}", 3000)
            return
        self._open_crop_editor(path, None)

    def _capture_screen_from_menu(self):
        self._show_ai_panel_impl()
        self.root.after(120, self._capture_screen_for_chat)

    def _ask_screen_question(self, text_widget, question, screenshot_path=None):
        text_widget.delete("1.0", "end")
        text_widget.configure(height=2)
        if not screenshot_path:
            try:
                screenshot_path = self.capture_screen_context()
            except Exception as exc:
                self._show_toast_impl(f"Screenshot failed: {exc}", 3000)
                return
        self.screen_context_path = screenshot_path
        self.ai_messages.append({"role": "user", "text": question, "image_path": screenshot_path, "can_crop": False})
        pending = {"role": "assistant", "text": "Reading screenshot", "pending": True}
        self.ai_messages.append(pending)
        self._append_ai_message(self.ai_messages[-2])
        self._append_ai_message(self.ai_messages[-1])
        self._scroll_ai_to_bottom()
        threading.Thread(target=self._read_screen_in_background, args=(question, screenshot_path, pending), daemon=True).start()

    def _attach_screen_to_input(self, path):
        self.pending_screen_path = path
        self.screen_context_path = path
        self._render_pending_attachment()

    def _remove_pending_attachment(self):
        self.pending_screen_path = None
        self._render_pending_attachment()

    def _render_pending_attachment(self):
        if self.ai_attachment_frame is None:
            return
        for child in self.ai_attachment_frame.winfo_children():
            child.destroy()
        self.ai_attachment_photo = None
        if not self.pending_screen_path:
            self.ai_attachment_frame.pack_forget()
            self._queue_ai_layout_refresh()
            return
        try:
            from PIL import Image, ImageTk

            image = Image.open(self.pending_screen_path)
            image.thumbnail((112, 64))
            self.ai_attachment_photo = ImageTk.PhotoImage(image)
        except Exception:
            self.ai_attachment_frame.pack_forget()
            self._queue_ai_layout_refresh()
            return
        if not self.ai_attachment_frame.winfo_ismapped():
            if self.ai_chat_text_widget is not None and self.ai_chat_text_widget.winfo_exists():
                self.ai_attachment_frame.pack(fill="x", before=self.ai_chat_text_widget)
            else:
                self.ai_attachment_frame.pack(fill="x")
        card = tk.Frame(self.ai_attachment_frame, bg="#1f1f1f", padx=10, pady=7)
        card.pack(anchor="w", pady=(0, 6))
        tk.Label(card, image=self.ai_attachment_photo, bg="#1f1f1f").pack(side="left")
        meta = tk.Frame(card, bg="#1f1f1f")
        meta.pack(side="left", padx=(10, 0))
        tk.Label(meta, text="Screenshot attached", bg="#1f1f1f", fg="#ffffff", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Button(meta, text="Remove", command=self._remove_pending_attachment, bg="#2b2b2b", fg="#dddddd", relief="flat", padx=10, pady=5, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
        self._lock_panel_size(self.ai_panel)
        self._queue_ai_layout_refresh()

    def _read_screen_in_background(self, question, screenshot_path, pending):
        response = self.ask_screen_context(question, screenshot_path)
        if self.ai_panel is not None:
            self.ai_panel.after(0, lambda: self._finish_screen_answer(pending, response))

    def _finish_screen_answer(self, pending, response):
        pending["text"] = response
        pending.pop("pending", None)
        self._update_last_ai_message(response)

    def _screenshot_preview(self, parent, path, message=None):
        try:
            from PIL import Image, ImageTk

            image = Image.open(path)
            image.thumbnail((620, 360))
            photo = ImageTk.PhotoImage(image)
        except Exception:
            return
        self.ai_image_refs.append(photo)
        align = "e" if message and message.get("role") == "user" else "w"
        outer = tk.Frame(parent, bg="#101010")
        outer.pack(fill="x", pady=(0, 5))
        frame = tk.Frame(outer, bg="#101010")
        frame.pack(anchor=align, padx=(90, 0) if align == "e" else (0, 90))
        tk.Label(frame, image=photo, bg="#101010").pack(anchor=align)
        return outer

    def _open_crop_editor(self, path, message):
        try:
            from PIL import Image, ImageTk

            image = Image.open(path).convert("RGB")
        except Exception as exc:
            self._show_toast_impl(f"Could not open screenshot: {exc}", 3000)
            return

        editor = tk.Toplevel(self.ai_panel or self.root)
        editor.title("Screenshot Markup")
        editor.configure(bg="#101010")
        editor.attributes("-topmost", True)
        editor.resizable(False, False)

        max_width, max_height = screenshot_editor_preview_limits(
            editor.winfo_screenwidth(),
            editor.winfo_screenheight(),
        )
        scale = min(max_width / image.width, max_height / image.height, 1.0)
        display_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        display_image = image.resize(display_size)
        photo = ImageTk.PhotoImage(display_image)
        editor.photo_ref = photo

        header = tk.Frame(editor, bg="#101010", padx=14, pady=10)
        header.pack(fill="x")
        title = tk.Frame(header, bg="#101010")
        title.pack(side="left", fill="x", expand=True)
        tk.Label(title, text="Screenshot markup", bg="#101010", fg="#ffffff", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(
            title,
            text="Crop if needed, mark a specific area, or place a note. Done copies the result.",
            bg="#101010",
            fg="#9ca3af",
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(1, 0))

        tools = tk.Frame(editor, bg="#171717", padx=14, pady=8)
        tools.pack(fill="x", padx=14, pady=(0, 8))
        tool_var = tk.StringVar(value="rectangle")
        color_var = tk.StringVar(value="#2563eb")
        note_var = tk.StringVar()
        annotations = []
        selection = {"start": None, "end": None, "item": None}
        active = {"start": None, "item": None, "kind": None}
        tool_buttons = {}
        color_buttons = {}

        def refresh_buttons():
            for name, button in tool_buttons.items():
                button.configure(bg="#334155" if tool_var.get() == name else "#242424")
            for color, button in color_buttons.items():
                button.configure(relief="sunken" if color_var.get() == color else "flat", borderwidth=2 if color_var.get() == color else 0)

        def choose_tool(name):
            tool_var.set(name)
            refresh_buttons()

        tk.Label(tools, text="TOOLS", bg="#171717", fg="#9ca3af", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 8))
        for name, label in (("crop", "Crop"), ("rectangle", "Rectangle"), ("ellipse", "Ellipse"), ("arrow", "Arrow"), ("text", "Text")):
            button = tk.Button(
                tools,
                text=label,
                command=lambda value=name: choose_tool(value),
                bg="#242424",
                fg="#ffffff",
                activebackground="#334155",
                activeforeground="#ffffff",
                relief="flat",
                padx=9,
                pady=5,
                font=("Segoe UI", 8),
            )
            button.pack(side="left", padx=(0, 5))
            tool_buttons[name] = button

        tk.Label(tools, text="COLOR", bg="#171717", fg="#9ca3af", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(10, 7))
        for color, label in (("#2563eb", "Blue"), ("#ef4444", "Red")):
            button = tk.Button(
                tools,
                text=label,
                command=lambda value=color: (color_var.set(value), refresh_buttons()),
                bg=color,
                fg="#ffffff",
                activebackground=color,
                activeforeground="#ffffff",
                relief="flat",
                padx=9,
                pady=5,
                font=("Segoe UI", 8, "bold"),
            )
            button.pack(side="left", padx=(0, 5))
            color_buttons[color] = button

        note_row = tk.Frame(editor, bg="#101010", padx=14)
        note_row.pack(fill="x", pady=(0, 8))
        tk.Label(note_row, text="Note", bg="#101010", fg="#d1d5db", font=("Segoe UI", 8, "bold")).pack(side="left", padx=(0, 7))
        note_entry = tk.Entry(
            note_row,
            textvariable=note_var,
            bg="#202020",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            font=("Segoe UI", 9),
        )
        note_entry.pack(side="left", fill="x", expand=True, ipady=5)
        tk.Label(note_row, text="Select Text, then click where the note should appear.", bg="#101010", fg="#737373", font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))

        canvas = tk.Canvas(editor, width=display_size[0], height=display_size[1], bg="#050505", highlightthickness=0, cursor="crosshair")
        canvas.pack(padx=14, pady=(0, 10))
        canvas.create_image(0, 0, anchor="nw", image=photo)

        def clamp_point(event):
            return (
                max(0, min(display_size[0], event.x)),
                max(0, min(display_size[1], event.y)),
            )

        def start_draw(event):
            x, y = clamp_point(event)
            kind = tool_var.get()
            if kind == "text":
                note = note_var.get().strip()
                if not note:
                    self._show_toast_impl("Type a note first.", 1800)
                    note_entry.focus_set()
                    return
                item = canvas.create_text(x, y, text=note, anchor="nw", fill=color_var.get(), font=("Segoe UI", 14, "bold"))
                annotations.append(
                    {
                        "kind": "text",
                        "x1": x / scale,
                        "y1": y / scale,
                        "text": note,
                        "color": color_var.get(),
                        "font_size": max(18, int(20 / scale)),
                        "canvas_item": item,
                    }
                )
                note_var.set("")
                return
            active.update({"start": (x, y), "kind": kind, "item": None})
            if kind == "crop":
                if selection["item"] is not None:
                    canvas.delete(selection["item"])
                selection.update({"start": (x, y), "end": (x, y)})
                active["item"] = canvas.create_rectangle(x, y, x, y, outline="#ffffff", width=2, dash=(6, 4))
                selection["item"] = active["item"]
            elif kind == "rectangle":
                active["item"] = canvas.create_rectangle(x, y, x, y, outline=color_var.get(), width=2)
            elif kind == "ellipse":
                active["item"] = canvas.create_oval(x, y, x, y, outline=color_var.get(), width=2)
            elif kind == "arrow":
                active["item"] = canvas.create_line(
                    x,
                    y,
                    x,
                    y,
                    fill=color_var.get(),
                    width=2,
                    arrow=tk.LAST,
                    arrowshape=(12, 14, 5),
                )

        def update_draw(event):
            if active["start"] is None or active["item"] is None:
                return
            x, y = clamp_point(event)
            canvas.coords(active["item"], active["start"][0], active["start"][1], x, y)
            if active["kind"] == "crop":
                selection["end"] = (x, y)

        def finish_draw(event):
            if active["start"] is None or active["item"] is None:
                return
            x, y = clamp_point(event)
            start_x, start_y = active["start"]
            canvas.coords(active["item"], start_x, start_y, x, y)
            if active["kind"] != "crop":
                distance = math.hypot(x - start_x, y - start_y)
                too_small = distance < 8 if active["kind"] == "arrow" else abs(x - start_x) < 5 or abs(y - start_y) < 5
                if too_small:
                    canvas.delete(active["item"])
                else:
                    annotations.append(
                        {
                            "kind": active["kind"],
                            "x1": start_x / scale,
                            "y1": start_y / scale,
                            "x2": x / scale,
                            "y2": y / scale,
                            "color": color_var.get(),
                            "width": max(2, int(2 / scale)),
                            "canvas_item": active["item"],
                        }
                    )
            active.update({"start": None, "item": None, "kind": None})

        def undo():
            if annotations:
                annotation = annotations.pop()
                canvas.delete(annotation.get("canvas_item"))
            elif selection["item"] is not None:
                canvas.delete(selection["item"])
                selection.update({"start": None, "end": None, "item": None})

        def finish_markup():
            box = None
            if selection["start"] is not None and selection["end"] is not None:
                box = scaled_crop_box(
                    selection["start"][0],
                    selection["start"][1],
                    selection["end"][0],
                    selection["end"][1],
                    scale,
                    image.width,
                    image.height,
                )
                if box is None:
                    self._show_toast_impl("Crop area is too small.", 1800)
                    return
            output = render_screenshot_annotations(image, annotations, box)
            base, _ = os.path.splitext(path)
            output_path = f"{base}-marked-{int(time.time())}.png"
            output.save(output_path)
            try:
                copy_image_to_clipboard(output)
            except Exception as exc:
                self._show_toast_impl(f"Saved, but clipboard copy failed: {exc}", 3000)
            if message is None:
                self._attach_screen_to_input(output_path)
            else:
                self.screen_context_path = output_path
                message["image_path"] = output_path
                message["text"] = "Screenshot markup ready."
                self._render_ai_messages()
            editor.destroy()
            self._show_toast_impl("Screenshot copied to clipboard and attached.", 2200)

        tk.Button(header, text="Cancel", command=editor.destroy, bg="#242424", fg="#dddddd", relief="flat", padx=9, pady=5, font=("Segoe UI", 8)).pack(side="right", padx=(6, 0))
        tk.Button(header, text="Done & Copy", command=finish_markup, bg="#2563eb", fg="#ffffff", relief="flat", padx=12, pady=5, font=("Segoe UI", 8, "bold")).pack(side="right")
        tk.Button(header, text="Undo", command=undo, bg="#242424", fg="#dddddd", relief="flat", padx=9, pady=5, font=("Segoe UI", 8)).pack(side="right", padx=(0, 6))

        canvas.bind("<ButtonPress-1>", start_draw)
        canvas.bind("<B1-Motion>", update_draw)
        canvas.bind("<ButtonRelease-1>", finish_draw)
        editor.bind("<Control-z>", lambda _event: undo())
        editor.bind("<Escape>", lambda _event: editor.destroy())
        refresh_buttons()
        editor.update_idletasks()
        window_width = editor.winfo_reqwidth()
        window_height = editor.winfo_reqheight()
        x = max(20, (editor.winfo_screenwidth() - window_width) // 2)
        y = max(20, (editor.winfo_screenheight() - window_height) // 2)
        editor.geometry(f"{window_width}x{window_height}+{x}+{y}")
        editor.lift()
        try:
            editor.focus_force()
        except Exception:
            pass

    def _empty_ai_state(self, parent):
        frame = tk.Frame(parent, bg="#101010", pady=18)
        frame.pack(fill="x")
        tk.Label(
            frame,
            text="Ask me anything.",
            bg="#101010",
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))
        tk.Label(
            frame,
            text="Type below, capture a screenshot, or ask about what is on your screen.",
            bg="#101010",
            fg="#a3a3a3",
            font=("Segoe UI", 12),
            anchor="w",
            wraplength=430,
            justify="left",
        ).pack(fill="x")

    def _panel_label(self, parent, text, size, color, bold=False):
        font = ("Segoe UI", size, "bold") if bold else ("Segoe UI", size)
        label = tk.Label(parent, text=text, bg=parent["bg"], fg=color, font=font, justify="left", anchor="w", wraplength=700)
        label.pack(fill="x", pady=(0, 4))
        return label

    def _panel_size(self, window):
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        width = min(AI_PANEL_W, screen_width - AI_PANEL_MARGIN * 2)
        height = min(AI_PANEL_H, screen_height - AI_PANEL_MARGIN * 2)
        return width, height

    def _panel_geometry(self, window):
        width, height = self._panel_size(window)
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x = max(0, screen_width - width - AI_PANEL_MARGIN)
        y = max(AI_PANEL_MARGIN, (screen_height - height) // 2)
        return width, height, x, y

    def _section_label(self, parent, text):
        label = tk.Label(parent, text=text.upper(), bg=parent["bg"], fg="#8f8f8f", font=("Segoe UI", 10, "bold"), anchor="w")
        label.pack(fill="x", pady=(18, 8))
        return label

    def _chat_bubble(self, parent, text, role, pending=False):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", pady=(0, 10))
        align = "e" if role == "user" else "w"
        is_thinking = pending and role == "assistant"
        bubble_bg = parent["bg"] if is_thinking else ("#2563eb" if role == "user" else "#1a1a1a")
        bubble_fg = "#9ca3af" if is_thinking else ("#ffffff" if role == "user" else "#e5e5e5")
        bubble = tk.Frame(row, bg=bubble_bg, padx=5 if is_thinking else 13, pady=8 if is_thinking else 9)
        bubble.pack(anchor=align, padx=(110, 0) if role == "user" else (0, 110))
        copy_button = None
        if role == "assistant":
            copy_button = tk.Button(
                bubble,
                text="⧉",
                command=lambda value=text: self._copy_chat_message(value),
                bg=bubble_bg,
                fg="#a3a3a3",
                activebackground="#262626",
                activeforeground="#ffffff",
                relief="flat",
                borderwidth=0,
                padx=4,
                pady=0,
                font=("Segoe UI Symbol", 13),
                cursor="hand2",
            )
            if not is_thinking:
                copy_button.pack(anchor="e", pady=(0, 2))
        label = tk.Label(
            bubble,
            text=thinking_display_text(text, 0) if is_thinking else format_chat_display_text(text),
            bg=bubble_bg,
            fg=bubble_fg,
            font=("Segoe UI", AI_PENDING_FONT_SIZE, "italic") if is_thinking else ("Segoe UI", AI_REPLY_FONT_SIZE),
            justify="left",
            wraplength=590,
        )
        label.pack()
        label.thinking = is_thinking
        label.thinking_base = (text or "Thinking").strip().rstrip(".")
        if is_thinking:
            label.after(350, lambda: self._animate_thinking_label(label, 1))
        bubble.message_label = label
        bubble.copy_button = copy_button
        return bubble

    def _copy_chat_message(self, text):
        import pyperclip

        pyperclip.copy(format_chat_display_text(text))
        self._show_toast_impl("Reply copied.", 1400)

    def _animate_thinking_label(self, label, step):
        try:
            if not label.winfo_exists() or not getattr(label, "thinking", False):
                return
            label.configure(text=thinking_display_text(label.thinking_base, step))
            label.after(350, lambda: self._animate_thinking_label(label, step + 1))
        except Exception:
            return

    def _scroll_ai_with_wheel(self, event):
        if self.ai_canvas is None or not self.ai_canvas.winfo_exists():
            return
        if getattr(event, "num", None) == 4:
            steps = -3
        elif getattr(event, "num", None) == 5:
            steps = 3
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return
            steps = -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120)
        self.ai_canvas.yview_scroll(steps, "units")

    def _copy_text_widget(self, text_widget):
        import pyperclip

        pyperclip.copy(text_widget.get("1.0", "end").strip())
        self._show_toast_impl("Draft copied.", 1800)

    def _open_gmail_search(self, result):
        message_id = result.get("message_id") or ""
        if message_id:
            webbrowser.open(f"https://mail.google.com/mail/u/0/#all/{quote_plus(message_id)}")
            return
        subject = result.get("subject") or ""
        webbrowser.open(f"https://mail.google.com/mail/u/0/#search/{quote_plus(subject)}")

    def _bind_mousewheel(self, canvas):
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def bind(_event):
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind(_event):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", bind)
        canvas.bind("<Leave>", unbind)

    def _clamp_height(self, dx, width, height):
        top = FLOOR - height
        for point_x in [CX + dx, CX + dx + width - 1]:
            max_dy = math.sqrt(max(0, (R - 8) ** 2 - (point_x - CX) ** 2))
            top = max(top, CY - int(max_dy))
        return max(4, FLOOR - top)

    def _build_canvas(self):
        self.canvas.delete("all")
        self.pulse_ring = self.canvas.create_oval(
            CX-OUTER_RING_RADIUS,
            CY-OUTER_RING_RADIUS,
            CX+OUTER_RING_RADIUS,
            CY+OUTER_RING_RADIUS,
            fill="",
            outline="#2a2a2a",
            width=1,
        )
        self.orb_body = self.canvas.create_oval(CX-R, CY-R, CX+R, CY+R, fill="#111111", outline="#555555", width=2)
        self.idle_heights = [self._clamp_height(bar["dx"], bar["w"], bar["baseH"]) for bar in BLDS]
        self.bar_rects = []
        for index, bar in enumerate(BLDS):
            x = CX + bar["dx"]
            rectangle = self.canvas.create_rectangle(x, FLOOR-self.idle_heights[index], x+bar["w"], FLOOR, fill=SHADES[index], outline="")
            self.bar_rects.append(rectangle)
        self.canvas.create_oval(CX-R+4, CY-R+4, CX+R-4, CY+R-4, fill="", outline="#2d2d2d", width=1)
        self.state_label = self.canvas.create_text(CX, CY+R+22, text="", fill="#d4d4d4", font=("Segoe UI", 9, "bold"))

    def _reset_logo_bars(self):
        for index, (bar, rectangle) in enumerate(zip(BLDS, self.bar_rects)):
            x = CX + bar["dx"]
            self.canvas.coords(rectangle, x, FLOOR-self.idle_heights[index], x+bar["w"], FLOOR)
            self.canvas.itemconfig(rectangle, fill=SHADES[index])

    def _enforce_orb_size(self, event):
        """Keep the transparent orb canvas identical in every app state."""
        if self.orb_size_clamping or event.width == ORB_W and event.height == ORB_H:
            return
        self.orb_size_clamping = True
        x, y = self.root.winfo_x(), self.root.winfo_y()
        self.root.geometry(f"{ORB_W}x{ORB_H}+{x}+{y}")
        self.root.after_idle(lambda: setattr(self, "orb_size_clamping", False))

    def _update_canvas(self, state):
        fills = {
            "idle": "#111111",
            "recording": "#1b1b1b",
            "cleaning": "#202020",
            "thinking": "#202020",
            "typing": "#181818",
            "done": "#151515",
        }
        self.canvas.itemconfig(self.orb_body, fill=fills.get(state, "#111111"))
        if state in ("recording", "thinking", "cleaning"):
            for index, (bar, rectangle) in enumerate(zip(BLDS, self.bar_rects)):
                height = self._clamp_height(
                    bar["dx"],
                    bar["w"],
                    animated_bar_height(bar, self.anim_t, state),
                )
                x = CX + bar["dx"]
                self.canvas.coords(rectangle, x, FLOOR-height, x+bar["w"], FLOOR)
                self.canvas.itemconfig(rectangle, fill=SHADES[index])
        else:
            self._reset_logo_bars()

        radius, color, width = pulse_ring_style(state, self.anim_t)
        self.canvas.coords(
            self.pulse_ring,
            CX-radius,
            CY-radius,
            CX+radius,
            CY+radius,
        )
        self.canvas.itemconfig(self.pulse_ring, outline=color, width=width)

        labels = {
            "idle": "",
            "recording": "REC",
            "cleaning": "CLEAN",
            "thinking": "THINK",
            "typing": "TYPE",
            "done": "DONE",
        }
        self.canvas.itemconfig(self.state_label, text=labels.get(state, ""))
        self.previous_state = state

    def _animate_loop(self):
        now = time.time()
        delta = 0.05 if self.last_anim_time == 0 else min(0.1, now - self.last_anim_time)
        self.anim_t += delta * 1.4
        self.last_anim_time = now
        self._update_canvas(self.orb_state)
        self.root.after(30, self._animate_loop)

    def _show_context_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, **MENU_STYLE)
        history_menu = tk.Menu(menu, tearoff=0, **MENU_STYLE)
        entries = self.list_history()
        if entries:
            for index, entry in enumerate(entries):
                history_menu.add_command(label=entry["label"], command=lambda item=index: self.copy_history(item))
        else:
            history_menu.add_command(label="No recent results", state="disabled")
        history_menu.add_separator()
        history_menu.add_command(label="Clear history...", command=self.clear_history)
        menu.add_cascade(label="Recent Results", menu=history_menu)
        menu.add_separator()
        rewrite_menu = tk.Menu(menu, tearoff=0, **MENU_STYLE)
        for label, instruction in self.rewrite_actions:
            rewrite_menu.add_command(label=label, command=lambda text=instruction: self.rewrite_clipboard(text))
        rewrite_menu.add_separator()
        rewrite_menu.add_command(label="Custom instruction...", command=self.custom_rewrite)
        menu.add_cascade(label="Rewrite Clipboard", menu=rewrite_menu)
        menu.add_separator()
        menu.add_command(label="Settings...", command=self.open_settings)
        menu.add_command(label="Diagnostics...", command=self.open_diagnostics)
        menu.add_command(label="Setup...", command=self.open_onboarding)
        menu.add_command(label="VoiceFlow AI", command=self.open_ai_panel)
        menu.add_command(label="Screenshot & Markup", command=self._capture_screen_from_menu)
        menu.add_command(label="Conversation — coming soon", state="disabled")
        menu.add_separator()
        startup_var = tk.BooleanVar(value=self.is_startup_enabled())
        menu.add_checkbutton(label="Start VoiceFlow with Windows", variable=startup_var, command=self.toggle_startup)
        menu.add_separator()
        menu.add_command(label="Change API Key...", command=self.change_api_key)
        menu.add_command(label="OpenAI Realtime API Key...", command=self.change_openai_realtime_api_key)
        menu.add_command(label="Reconnect AI", command=self._reconnect_ai_from_menu)
        menu.add_separator()
        menu.add_command(label="Open log file", command=self.open_log)
        menu.add_separator()
        menu.add_command(label="Quit", command=self.close_app)
        menu.tk_popup(event.x_root, event.y_root)

    def _reconnect_ai_from_menu(self):
        def run():
            message = self.reconnect_ai()
            self.show_toast(message, 3000)

        threading.Thread(target=run, daemon=True).start()

    def _start_move(self, event):
        self.drag_x, self.drag_y = event.x, event.y

    def _do_move(self, event):
        self.root.geometry(f"+{self.root.winfo_x()+event.x-self.drag_x}+{self.root.winfo_y()+event.y-self.drag_y}")
