import queue
import tkinter as tk


class ConversationWindow:
    def __init__(self, root, start_session, stop_session, set_muted):
        self.root = root
        self.start_session = start_session
        self.stop_session = stop_session
        self.set_muted = set_muted
        self.window = None
        self.events = queue.Queue()
        self.messages = []
        self.active = {"user": None, "assistant": None}
        self.muted = False
        self.status_label = None
        self.transcript = None
        self.mute_button = None

    def open(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return

        self.window = tk.Toplevel(self.root)
        self.window.title("Aylo Conversation")
        self.window.geometry("760x720")
        self.window.minsize(520, 520)
        self.window.configure(bg="#0b0b0d")
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        header = tk.Frame(self.window, bg="#111114", padx=22, pady=18)
        header.pack(fill="x")
        tk.Label(
            header,
            text="Conversation",
            bg="#111114",
            fg="#ffffff",
            font=("Segoe UI", 18, "bold"),
        ).pack(side="left")
        self.status_label = tk.Label(
            header,
            text="Connecting…",
            bg="#111114",
            fg="#93c5fd",
            font=("Segoe UI", 11),
        )
        self.status_label.pack(side="right")

        hint = tk.Label(
            self.window,
            text="Speak naturally. You can interrupt the assistant at any time.",
            bg="#0b0b0d",
            fg="#8b8b93",
            font=("Segoe UI", 10),
            padx=22,
            pady=12,
            anchor="w",
        )
        hint.pack(fill="x")

        transcript_frame = tk.Frame(self.window, bg="#0b0b0d", padx=18)
        transcript_frame.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(transcript_frame)
        scrollbar.pack(side="right", fill="y")
        self.transcript = tk.Text(
            transcript_frame,
            bg="#0b0b0d",
            fg="#ededf0",
            insertbackground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=12,
            wrap="word",
            font=("Segoe UI", 12),
            state="disabled",
            yscrollcommand=scrollbar.set,
        )
        self.transcript.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.transcript.yview)
        self.transcript.tag_configure("user_name", foreground="#60a5fa", font=("Segoe UI", 10, "bold"), spacing1=14)
        self.transcript.tag_configure("assistant_name", foreground="#a78bfa", font=("Segoe UI", 10, "bold"), spacing1=14)
        self.transcript.tag_configure("message", foreground="#ededf0", font=("Segoe UI", 13), spacing3=6)
        self.transcript.tag_configure("placeholder", foreground="#73737c", font=("Segoe UI", 13, "italic"))

        controls = tk.Frame(self.window, bg="#111114", padx=20, pady=16)
        controls.pack(fill="x")
        tk.Button(
            controls,
            text="Clear transcript",
            command=self.clear,
            bg="#25252a",
            fg="#e5e5e5",
            activebackground="#303036",
            activeforeground="#ffffff",
            relief="flat",
            padx=15,
            pady=9,
            font=("Segoe UI", 10),
        ).pack(side="left")
        self.mute_button = tk.Button(
            controls,
            text="Mute microphone",
            command=self.toggle_mute,
            bg="#25252a",
            fg="#e5e5e5",
            activebackground="#303036",
            activeforeground="#ffffff",
            relief="flat",
            padx=15,
            pady=9,
            font=("Segoe UI", 10),
        )
        self.mute_button.pack(side="right", padx=(10, 0))
        tk.Button(
            controls,
            text="End conversation",
            command=self.close,
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            padx=17,
            pady=9,
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right")

        self.window.after(50, self._drain_events)
        try:
            self.start_session(self.post_event)
        except Exception as exc:
            self.post_event("error", str(exc))

    def close(self):
        self.stop_session()
        if self.window and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
        self.messages = []
        self.active = {"user": None, "assistant": None}

    def post_event(self, kind, payload=None):
        self.events.put((kind, payload))

    def toggle_mute(self):
        self.muted = not self.muted
        self.set_muted(self.muted)
        self.mute_button.configure(text="Unmute microphone" if self.muted else "Mute microphone")
        self._set_status("Muted" if self.muted else "Listening")

    def clear(self):
        self.messages = []
        self.active = {"user": None, "assistant": None}
        self._render()

    def _drain_events(self):
        if not self.window or not self.window.winfo_exists():
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self._handle_event(kind, payload)
        except queue.Empty:
            pass
        self.window.after(50, self._drain_events)

    def _handle_event(self, kind, payload):
        if kind == "status":
            self._set_status(payload)
        elif kind == "error":
            self._set_status("Connection error", "#f87171")
            self._append_system(payload)
        elif kind == "speech_started":
            self.active["assistant"] = None
        elif kind == "transcript":
            self._update_transcript(payload)
        elif kind == "closed":
            self._set_status("Ended", "#a3a3a3")

    def _update_transcript(self, payload):
        role = payload.get("role", "assistant")
        text = payload.get("text") or ""
        final = bool(payload.get("final"))
        index = self.active.get(role)

        if index is None:
            if not text:
                return
            self.messages.append({"role": role, "text": text.strip() if final else text, "system": False})
            index = len(self.messages) - 1
            self.active[role] = index
        elif text:
            current = self.messages[index]["text"]
            if final:
                self.messages[index]["text"] = text
            else:
                self.messages[index]["text"] = current + text

        if final:
            self.active[role] = None
        self._render()

    def _append_system(self, text):
        self.messages.append({"role": "assistant", "text": text, "system": True})
        self._render()

    def _render(self):
        if not self.transcript or not self.transcript.winfo_exists():
            return
        self.transcript.configure(state="normal")
        self.transcript.delete("1.0", "end")
        if not self.messages:
            self.transcript.insert("end", "Your conversation will appear here.", "placeholder")
        for message in self.messages:
            role = message["role"]
            name = "YOU\n" if role == "user" else ("SYSTEM\n" if message.get("system") else "AYLO AI\n")
            self.transcript.insert("end", name, f"{role}_name")
            self.transcript.insert("end", message["text"].strip() + "\n", "message")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")

    def _set_status(self, text, color="#93c5fd"):
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=text, fg=color)
