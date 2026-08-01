import tkinter as tk
import tkinter.messagebox as messagebox
from tkinter import ttk


SENSITIVITY_OPTIONS = {
    "High - quieter speech": 0.0002,
    "Normal": 0.0008,
    "Low - noisy rooms": 0.002,
}
def sensitivity_label(threshold):
    return min(SENSITIVITY_OPTIONS, key=lambda label: abs(SENSITIVITY_OPTIONS[label] - threshold))


class SettingsWindow:
    def __init__(self, parent, settings, input_devices, save_callback, ai_key_configured=False, change_api_key_callback=None):
        self.settings = settings
        self.input_devices = input_devices
        self.save_callback = save_callback
        self.change_api_key_callback = change_api_key_callback
        self.device_by_label = {device["label"]: device["id"] for device in input_devices}

        self.window = tk.Toplevel(parent)
        self.window.title("VoiceFlow Settings")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#1a1a1a")

        body = tk.Frame(self.window, bg="#1a1a1a", padx=16, pady=16)
        body.pack()

        tk.Label(body, text="Microphone", bg="#1a1a1a", fg="#dddddd", anchor="w").grid(row=0, column=0, sticky="w")
        self.device_var = tk.StringVar(value=self._current_device_label())
        self.device_select = ttk.Combobox(body, textvariable=self.device_var, values=list(self.device_by_label), width=44, state="readonly")
        self.device_select.grid(row=1, column=0, columnspan=2, pady=(4, 12), sticky="ew")

        tk.Label(body, text="Speech sensitivity", bg="#1a1a1a", fg="#dddddd", anchor="w").grid(row=2, column=0, sticky="w")
        self.sensitivity_var = tk.StringVar(value=sensitivity_label(settings.silence_rms_threshold))
        self.sensitivity_select = ttk.Combobox(body, textvariable=self.sensitivity_var, values=list(SENSITIVITY_OPTIONS), width=44, state="readonly")
        self.sensitivity_select.grid(row=3, column=0, columnspan=2, pady=(4, 12), sticky="ew")

        tk.Label(body, text="Maximum recording duration", bg="#1a1a1a", fg="#dddddd", anchor="w").grid(row=4, column=0, sticky="w")
        self.duration_var = tk.StringVar(value=str(settings.max_record_seconds))
        self.duration_select = ttk.Combobox(body, textvariable=self.duration_var, values=["15", "30", "45", "60"], width=44, state="readonly")
        self.duration_select.grid(row=5, column=0, columnspan=2, pady=(4, 16), sticky="ew")

        self.ai_features_var = tk.BooleanVar(value=settings.ai_features_enabled)
        ai_frame = tk.LabelFrame(body, text="AI Features", bg="#1a1a1a", fg="#ffffff", padx=10, pady=8)
        ai_frame.grid(row=6, column=0, columnspan=2, pady=(0, 14), sticky="ew")
        tk.Checkbutton(
            ai_frame,
            text="Enable AI features",
            variable=self.ai_features_var,
            bg="#1a1a1a",
            fg="#ffffff",
            activebackground="#1a1a1a",
            activeforeground="#ffffff",
            selectcolor="#111111",
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            ai_frame,
            text="Off keeps VoiceFlow fully offline. On enables Ctrl + Space AI commands. Right Shift dictation always stays local.",
            bg="#1a1a1a", fg="#a3a3a3", wraplength=410, justify="left",
        ).pack(anchor="w", pady=(4, 7))
        status = "AI key: connected" if ai_key_configured else "AI key: not added"
        tk.Label(ai_frame, text=status, bg="#1a1a1a", fg="#86efac" if ai_key_configured else "#facc15").pack(side="left")
        if self.change_api_key_callback:
            tk.Button(ai_frame, text="Add / Update API Key", command=self.change_api_key_callback, bg="#333333", fg="#dddddd", relief="flat", padx=10, pady=5).pack(side="right")

        self.mouse_side_button_var = tk.BooleanVar(value=settings.mouse_side_button_mic)
        tk.Checkbutton(
            body,
            text="Use mouse side buttons for dictation and AI commands",
            variable=self.mouse_side_button_var,
            bg="#1a1a1a",
            fg="#dddddd",
            activebackground="#1a1a1a",
            activeforeground="#ffffff",
            selectcolor="#111111",
            anchor="w",
        ).grid(row=7, column=0, columnspan=2, pady=(0, 12), sticky="w")

        instructions = (
            "How to use: Hold Right Shift to dictate. Hold Ctrl + Space for an AI command when AI Features is on. "
            "Mouse Back dictates; Mouse Forward runs an AI command."
        )
        tk.Label(body, text=instructions, bg="#1a1a1a", fg="#a3a3a3", wraplength=430, justify="left").grid(
            row=8, column=0, columnspan=2, pady=(0, 14), sticky="w"
        )

        tk.Button(body, text="Cancel", command=self.window.destroy, bg="#333333", fg="#dddddd", relief="flat", padx=12).grid(row=9, column=0, sticky="e", padx=(0, 6))
        tk.Button(body, text="Save", command=self._save, bg="#2563eb", fg="#ffffff", relief="flat", padx=12).grid(row=9, column=1, sticky="w")

        self.window.transient(parent)
        self.window.grab_set()

    def _current_device_label(self):
        for device in self.input_devices:
            if device["id"] == self.settings.mic_device:
                return device["label"]
        return self.input_devices[0]["label"]

    def _save(self):
        try:
            self.save_callback(
                mic_device=self.device_by_label[self.device_var.get()],
                silence_rms_threshold=SENSITIVITY_OPTIONS[self.sensitivity_var.get()],
                max_record_seconds=int(self.duration_var.get()),
                mouse_side_button_mic=self.mouse_side_button_var.get(),
                mouse_forward_action="command",
                ai_features_enabled=self.ai_features_var.get(),
            )
        except Exception as exc:
            messagebox.showerror("VoiceFlow Settings", str(exc), parent=self.window)
            return
        messagebox.showinfo("VoiceFlow Settings", "Settings saved.", parent=self.window)
        self.window.destroy()


class DiagnosticsWindow:
    def __init__(self, parent, status_callback, reconnect_callback, open_log_callback):
        self.status_callback = status_callback
        self.reconnect_callback = reconnect_callback
        self.open_log_callback = open_log_callback
        self.window = tk.Toplevel(parent)
        self.window.title("VoiceFlow Diagnostics")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#111111")

        body = tk.Frame(self.window, bg="#111111", padx=18, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Diagnostics", bg="#111111", fg="#ffffff", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        self.rows = tk.Frame(body, bg="#111111")
        self.rows.pack(fill="x", pady=(12, 14))

        actions = tk.Frame(body, bg="#111111")
        actions.pack(fill="x")
        tk.Button(actions, text="Reconnect AI", command=self._reconnect, bg="#2563eb", fg="#ffffff", relief="flat", padx=14, pady=8).pack(side="left")
        tk.Button(actions, text="Refresh", command=self.refresh, bg="#333333", fg="#dddddd", relief="flat", padx=14, pady=8).pack(side="left", padx=(8, 0))
        tk.Button(actions, text="Open Log", command=open_log_callback, bg="#333333", fg="#dddddd", relief="flat", padx=14, pady=8).pack(side="left", padx=(8, 0))
        tk.Button(actions, text="Close", command=self.window.destroy, bg="#333333", fg="#dddddd", relief="flat", padx=14, pady=8).pack(side="right")

        self.refresh()
        self.window.transient(parent)

    def refresh(self):
        for child in self.rows.winfo_children():
            child.destroy()
        status = self.status_callback()
        for label, value, ok in status:
            row = tk.Frame(self.rows, bg="#111111")
            row.pack(fill="x", pady=3)
            color = "#86efac" if ok else "#fca5a5"
            tk.Label(row, text=label, bg="#111111", fg="#d4d4d4", width=18, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg="#111111", fg=color, anchor="w", wraplength=360, justify="left").pack(side="left", fill="x", expand=True)

    def _reconnect(self):
        message = self.reconnect_callback()
        messagebox.showinfo("VoiceFlow Diagnostics", message, parent=self.window)
        self.refresh()


class OnboardingWindow:
    def __init__(self, parent, settings, input_devices, save_callback, api_key_callback, reconnect_callback, finish_callback):
        self.settings = settings
        self.input_devices = input_devices
        self.save_callback = save_callback
        self.api_key_callback = api_key_callback
        self.reconnect_callback = reconnect_callback
        self.finish_callback = finish_callback
        self.device_by_label = {device["label"]: device["id"] for device in input_devices}

        self.window = tk.Toplevel(parent)
        self.window.title("Set Up VoiceFlow")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.window.configure(bg="#111111")
        width, height = 500, 380
        x = (self.window.winfo_screenwidth() - width) // 2
        y = (self.window.winfo_screenheight() - height) // 2
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(width, height)
        self.window.maxsize(width, height)

        body = tk.Frame(self.window, bg="#111111", padx=18, pady=18)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="Set Up VoiceFlow", bg="#111111", fg="#ffffff", font=("Segoe UI", 17, "bold")).pack(anchor="w")

        mic_frame = tk.Frame(body, bg="#111111")
        mic_frame.pack(fill="x", pady=(16, 12))
        tk.Label(mic_frame, text="Microphone", bg="#111111", fg="#dddddd", anchor="w").pack(anchor="w")
        self.device_var = tk.StringVar(value=self._current_device_label())
        ttk.Combobox(mic_frame, textvariable=self.device_var, values=list(self.device_by_label), width=48, state="readonly").pack(anchor="w", pady=(4, 8))
        tk.Button(mic_frame, text="Save Microphone", command=self._save_mic, bg="#333333", fg="#dddddd", relief="flat", padx=12, pady=7).pack(anchor="w")

        api_frame = tk.Frame(body, bg="#111111")
        api_frame.pack(fill="x", pady=(6, 12))
        tk.Label(api_frame, text="Groq API Key", bg="#111111", fg="#dddddd", anchor="w").pack(anchor="w")
        self.api_var = tk.StringVar()
        tk.Entry(api_frame, textvariable=self.api_var, show="*", width=52, bg="#1f1f1f", fg="#ffffff", insertbackground="#ffffff", relief="flat").pack(anchor="w", pady=(4, 8), ipady=5)
        tk.Button(api_frame, text="Save and Test AI", command=self._save_and_test_ai, bg="#2563eb", fg="#ffffff", relief="flat", padx=12, pady=7).pack(anchor="w")

        hint = "Try: hold the command hotkey and say, 'write a friendly follow-up email.'"
        tk.Label(body, text=hint, bg="#111111", fg="#a3a3a3", wraplength=440, justify="left").pack(anchor="w", pady=(8, 16))

        actions = tk.Frame(body, bg="#111111")
        actions.pack(fill="x")
        tk.Button(actions, text="Finish", command=self._finish, bg="#16a34a", fg="#ffffff", relief="flat", padx=18, pady=8).pack(side="right")
        tk.Button(actions, text="Skip", command=self._finish, bg="#333333", fg="#dddddd", relief="flat", padx=18, pady=8).pack(side="right", padx=(0, 8))

        self.window.transient(parent)
        self.window.lift()

    def _current_device_label(self):
        for device in self.input_devices:
            if device["id"] == self.settings.mic_device:
                return device["label"]
        return self.input_devices[0]["label"] if self.input_devices else ""

    def _save_mic(self):
        try:
            self.save_callback(
                mic_device=self.device_by_label[self.device_var.get()],
                silence_rms_threshold=self.settings.silence_rms_threshold,
                max_record_seconds=self.settings.max_record_seconds,
                mouse_side_button_mic=self.settings.mouse_side_button_mic,
                mouse_forward_action=self.settings.mouse_forward_action,
            )
        except Exception as exc:
            messagebox.showerror("VoiceFlow Setup", str(exc), parent=self.window)
            return
        messagebox.showinfo("VoiceFlow Setup", "Microphone saved.", parent=self.window)

    def _save_and_test_ai(self):
        key = self.api_var.get().strip()
        if key:
            self.api_key_callback(key)
        messagebox.showinfo("VoiceFlow Setup", self.reconnect_callback(), parent=self.window)

    def _finish(self):
        self.finish_callback()
        self.window.destroy()
