def get_active_window_title(log_error):
    try:
        import psutil
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd).lower()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process = psutil.Process(pid).name().lower()
        except Exception:
            process = ""
        return f"{title} {process}"
    except Exception as exc:
        log_error("Active window detection failed", exc)
        return ""
