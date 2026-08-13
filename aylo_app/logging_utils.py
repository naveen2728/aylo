import time
import traceback


def log_error(log_path, message, exc=None):
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        if exc:
            traceback.print_exc(file=handle)
