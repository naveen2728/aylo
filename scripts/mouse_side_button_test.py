"""Standalone tester for mouse side buttons.

Run:
    .venv\Scripts\python.exe scripts\mouse_side_button_test.py

Press the mouse Back/Forward side buttons. This script does not start
Aylo, record audio, paste text, or change app settings.
"""

from __future__ import annotations

import sys
import time

from pynput import mouse


SIDE_BUTTONS = {
    getattr(mouse.Button, "x1", None): "Back side button",
    getattr(mouse.Button, "x2", None): "Forward side button",
}
SIDE_BUTTONS = {button: label for button, label in SIDE_BUTTONS.items() if button is not None}


def main():
    if not SIDE_BUTTONS:
        raise SystemExit("This pynput version does not expose mouse side buttons.")

    print("Aylo mouse side-button test")
    print("Press Back/Forward side buttons on the mouse.")
    print("Press Ctrl+C here to stop.\n")

    pressed_at = {}

    def on_click(_x, _y, button, pressed):
        label = SIDE_BUTTONS.get(button)
        if not label:
            return
        now = time.monotonic()
        if pressed:
            pressed_at[button] = now
            print(f"{label}: DOWN")
            sys.stdout.flush()
            return
        started = pressed_at.pop(button, now)
        duration = now - started
        print(f"{label}: UP after {duration:.2f}s")
        sys.stdout.flush()

    with mouse.Listener(on_click=on_click) as listener:
        try:
            listener.join()
        except KeyboardInterrupt:
            listener.stop()
            print("\nStopped.")


if __name__ == "__main__":
    main()
