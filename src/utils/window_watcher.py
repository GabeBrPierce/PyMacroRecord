"""
WindowWatcher: polls the foreground (focused) window on a background thread and
reports its title + process name. Used to drive automatic profile switching.

Cross-platform backends:
  * Windows : ctypes (user32 / psapi) -- no extra dependency
  * Linux   : xdotool or wmctrl + /proc (optional, degrades gracefully)
  * macOS   : osascript (System Events)

The watcher never raises into the caller; if the platform tools are missing it
simply reports (None, None) and the rest of the app keeps working.
"""

import subprocess
from sys import platform
from threading import Event, Thread


def _windows_active_window():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None, None

    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    # Process name via PID
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if h:
        try:
            size = wintypes.DWORD(260)
            name_buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, name_buf, ctypes.byref(size)):
                full = name_buf.value
                process = full.replace("\\", "/").split("/")[-1]
        finally:
            kernel32.CloseHandle(h)
    return title, process


def _run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
        return out.stdout.strip()
    except Exception:
        return ""


def _linux_active_window():
    # Prefer xdotool (gives title + pid), fall back to wmctrl.
    title = _run(["xdotool", "getactivewindow", "getwindowname"])
    process = None
    pid = _run(["xdotool", "getactivewindow", "getwindowpid"])
    if pid:
        try:
            with open("/proc/%s/comm" % pid.split()[0], "r") as f:
                process = f.read().strip()
        except Exception:
            process = None
    if not title:
        # wmctrl fallback: the active window has the focus flag in -l is not given,
        # so we approximate with the first listed window. Best effort only.
        listing = _run(["wmctrl", "-l"])
        if listing:
            parts = listing.splitlines()[0].split(None, 3)
            if len(parts) == 4:
                title = parts[3]
    return (title or None), process


def _macos_active_window():
    script = (
        'tell application "System Events" to set p to name of first application '
        'process whose frontmost is true'
    )
    process = _run(["osascript", "-e", script]) or None
    title_script = (
        'tell application "System Events" to tell (first application process whose frontmost is true) '
        'to try\n return name of front window\n on error\n return ""\n end try'
    )
    title = _run(["osascript", "-e", title_script]) or None
    return title, process


def get_active_window():
    """Return (title, process_name); either may be None. Never raises."""
    try:
        if platform == "win32":
            return _windows_active_window()
        elif "linux" in platform.lower():
            return _linux_active_window()
        elif "darwin" in platform.lower():
            return _macos_active_window()
    except Exception:
        pass
    return None, None


def platform_supported():
    return platform == "win32" or "linux" in platform.lower() or "darwin" in platform.lower()


class WindowWatcher:
    def __init__(self, on_change, interval=0.7):
        """
        on_change(title, process) is called (from the watcher thread) whenever
        the focused window's title or process changes.
        """
        self.on_change = on_change
        self.interval = interval
        self._stop = Event()
        self._thread = None
        self._last = (None, None)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            current = get_active_window()
            if current != self._last and current != (None, None):
                self._last = current
                try:
                    self.on_change(*current)
                except Exception:
                    pass
            self._stop.wait(self.interval)
