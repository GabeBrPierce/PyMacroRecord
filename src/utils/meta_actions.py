"""
MetaActionExecutor: runs the "meta-bind" actions defined in library.META_ACTIONS.

Meta-binds let a hotkey trigger an application or system operation rather than
replaying a recording. They are profile-independent (always active) so they can
be used to switch profiles, panic-stop, or perform system operations.
"""

from os import system
from sys import platform


class MetaActionExecutor:
    def __init__(self, main_app):
        self.main_app = main_app

    @property
    def library(self):
        return self.main_app.library

    @property
    def macro(self):
        return self.main_app.macro

    def _status(self, text):
        try:
            self.main_app.after(0, lambda: self.main_app.status_text.configure(text=text))
        except Exception:
            pass

    def run(self, action, arg=None):
        """Dispatch a meta action. Called from the hotkey thread; UI changes are
        marshalled back onto the Tk thread via .after()."""
        handler = getattr(self, "_action_" + action, None)
        if handler is None:
            return
        try:
            handler(arg)
        except Exception as e:
            self._status("Meta-bind error: %s" % e)

    # ----------------------------------------------------------- profile ---
    def _action_switch_profile(self, arg):
        if arg and self.library.set_active_profile(arg):
            self._status("Active profile: %s" % arg)

    def _action_cycle_profile(self, arg):
        nxt = self.library.cycle_active_profile()
        self._status("Active profile: %s" % nxt)

    def _action_toggle_auto_switch(self, arg):
        state = self.library.toggle_auto_switch()
        self.main_app.after(0, self.main_app.refresh_auto_switch_var)
        self._status("Auto profile-switch: %s" % ("ON" if state else "OFF"))

    # ------------------------------------------------------------ macro ---
    def _action_play_recording(self, arg):
        if not arg:
            return
        profile, rec = self.library.find_recording(arg)
        if rec is None:
            return
        self.main_app.after(0, lambda: self.macro.play_library_recording(rec))

    def _action_stop_all(self, arg):
        if self.macro.playback:
            self.main_app.after(0, lambda: self.macro.stop_playback(True))
        if self.macro.record:
            self.main_app.after(0, self.macro.stop_record)

    def _action_panic(self, arg):
        # Stop everything and release any held keys/mouse buttons immediately.
        self.macro.playback = False
        self.macro.record = False
        try:
            self.macro.unPressEverything([])
        except Exception:
            pass
        self.main_app.after(0, lambda: self.macro.stop_playback(True))
        self.main_app.after(0, self.macro.reset_record_ui)
        self._status("PANIC: stopped")

    # ----------------------------------------------------------- system ---
    def _action_lock_computer(self, arg):
        if platform == "win32":
            system("rundll32.exe user32.dll,LockWorkStation")
        elif "linux" in platform.lower():
            system("loginctl lock-session || xdg-screensaver lock")
        elif "darwin" in platform.lower():
            system("pmset displaysleepnow")

    def _action_sleep_computer(self, arg):
        if platform == "win32":
            system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif "linux" in platform.lower():
            system("systemctl suspend")
        elif "darwin" in platform.lower():
            system("pmset sleepnow")
