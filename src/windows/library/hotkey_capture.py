"""A small modal dialog that captures a key combination using pynput and
returns it as a list of pynput key strings (e.g. ['Key.ctrl_l', 'f5'])."""

from tkinter import BOTTOM, LEFT, Button, Frame, Label, Toplevel

from pynput import keyboard, mouse

from utils.get_key_pressed import getKeyPressed, mouse_hotkey_token, display_keys


class HotkeyCapture(Toplevel):
    def __init__(self, parent, main_app, initial=None, title="Set hotkey"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.attributes("-topmost", 1)
        self.main_app = main_app
        self.result = "__cancel__"          # sentinel: dialog cancelled
        self._keys = list(initial or [])
        self._prev_prevent = getattr(main_app, "prevent_record", False)
        main_app.prevent_record = True

        Label(self, text="Press the key combination, then click OK.",
              padx=20, pady=10).pack()
        self.key_label = Label(self, text=self._format(), font=("Segoe UI", 13), pady=8)
        self.key_label.pack()

        btns = Frame(self)
        btns.pack(side=BOTTOM, pady=10)
        Button(btns, text="Clear", command=self._clear).pack(side=LEFT, padx=6)
        Button(btns, text="OK", command=self._ok).pack(side=LEFT, padx=6)
        Button(btns, text="Cancel", command=self._cancel).pack(side=LEFT, padx=6)

        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()
        self._mouse_listener = mouse.Listener(on_click=self._on_mouse)
        self._mouse_listener.start()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.geometry("+%d+%d" % (parent.winfo_rootx() + 60, parent.winfo_rooty() + 60))
        self.grab_set()
        self.wait_window()

    def _format(self):
        if not self._keys:
            return "(none)"
        return display_keys(self._keys)

    def _add(self, key_str):
        if key_str not in self._keys:
            self._keys.append(key_str)
            try:
                self.key_label.configure(text=self._format())
            except Exception:
                pass

    def _on_press(self, key):
        kp = getKeyPressed(self._listener, key)
        if kp is None:
            return
        # marshal back onto the Tk thread
        try:
            self.after(0, lambda: self._add(kp))
        except Exception:
            pass

    def _on_mouse(self, x, y, button, pressed):
        if not pressed:
            return
        token = mouse_hotkey_token(button)
        if token is None:
            return  # ignore left/right/middle for hotkeys
        try:
            self.after(0, lambda: self._add(token))
        except Exception:
            pass

    def _clear(self):
        self._keys = []
        self.key_label.configure(text=self._format())

    def _finish(self):
        try:
            self._listener.stop()
        except Exception:
            pass
        try:
            self._mouse_listener.stop()
        except Exception:
            pass
        self.main_app.prevent_record = self._prev_prevent
        self.destroy()

    def _ok(self):
        self.result = list(self._keys)
        self._finish()

    def _cancel(self):
        self.result = "__cancel__"
        self._finish()


def capture_hotkey(parent, main_app, initial=None, title="Set hotkey"):
    """Open the capture dialog. Returns a list (possibly empty) on OK, or None
    if the user cancelled."""
    dlg = HotkeyCapture(parent, main_app, initial=initial, title=title)
    if dlg.result == "__cancel__":
        return None
    return dlg.result
