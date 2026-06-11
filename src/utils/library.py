"""
Macro Library: profiles, recordings, per-recording hotkeys and meta-binds.

This module is intentionally free of any tkinter / pynput imports so its
logic can be unit-tested headlessly. All GUI and OS interaction lives
elsewhere (library_window.py, window_watcher.py, meta_actions.py).

Persistence is a single JSON file (library.json) stored next to
userSettings.json in the per-user config directory.
"""

import copy
import uuid
from json import dumps, load
from os import getenv, makedirs, path
from sys import platform
from time import time

GLOBAL_PROFILE = "Global"

# Meta-bind actions (the "practical set"). The GUI reads this to build menus;
# meta_actions.MetaActionExecutor knows how to run them.
META_ACTIONS = {
    "switch_profile":     {"label": "Switch to profile",       "needs_arg": "profile"},
    "cycle_profile":      {"label": "Cycle active profile",    "needs_arg": None},
    "play_recording":     {"label": "Play a recording",        "needs_arg": "recording"},
    "stop_all":           {"label": "Stop playback / record",  "needs_arg": None},
    "panic":              {"label": "Panic (stop + release)",  "needs_arg": None},
    "toggle_auto_switch": {"label": "Toggle auto profile-switch", "needs_arg": None},
    "lock_computer":      {"label": "Lock the computer",       "needs_arg": None},
    "sleep_computer":     {"label": "Sleep the computer",      "needs_arg": None},
}


def new_id():
    return uuid.uuid4().hex[:12]


def default_config_dir():
    """Mirror UserSettings path resolution so library.json sits next to settings."""
    if platform == "win32":
        return path.join(getenv("LOCALAPPDATA") or path.expanduser("~"), "PyMacroRecord")
    elif "linux" in platform.lower():
        return path.join(path.expanduser("~"), ".config", "PyMacroRecord")
    elif "darwin" in platform.lower():
        return path.join(path.expanduser("~"), "Library", "Application Support", "PyMacroRecord")
    return path.join(path.expanduser("~"), ".PyMacroRecord")


class Library:
    def __init__(self, main_app=None, config_dir=None):
        self.main_app = main_app
        self.path_setting = config_dir or default_config_dir()
        self.library_file = path.join(self.path_setting, "library.json")
        self._listeners = []
        self.data = self._load()
        self._ensure_structure()
        self.save()

    # ----------------------------------------------------------------- io ---
    @staticmethod
    def _default_data():
        return {
            "active_profile": GLOBAL_PROFILE,
            "auto_switch": False,
            "profiles": {
                GLOBAL_PROFILE: {"window_match": [], "recordings": {}}
            },
            "meta_binds": {},
        }

    def _load(self):
        try:
            if path.isfile(self.library_file):
                with open(self.library_file, "r", encoding="utf-8") as f:
                    return load(f)
        except Exception:
            pass
        return self._default_data()

    def _ensure_structure(self):
        d = self.data
        d.setdefault("profiles", {})
        d.setdefault("meta_binds", {})
        d.setdefault("auto_switch", False)
        if GLOBAL_PROFILE not in d["profiles"]:
            d["profiles"][GLOBAL_PROFILE] = {"window_match": [], "recordings": {}}
        for name, prof in d["profiles"].items():
            prof.setdefault("window_match", [])
            prof.setdefault("recordings", {})
            for rec in prof["recordings"].values():
                rec.setdefault("name", "Untitled")
                rec.setdefault("events", {"events": []})
                rec.setdefault("settings", None)
                rec.setdefault("hotkey", [])
                rec.setdefault("created", time())
        if d.get("active_profile") not in d["profiles"]:
            d["active_profile"] = GLOBAL_PROFILE

    def save(self):
        try:
            makedirs(self.path_setting, exist_ok=True)
            with open(self.library_file, "w", encoding="utf-8") as f:
                f.write(dumps(self.data, indent=2))
        except Exception:
            pass

    # ----------------------------------------------------------- listeners ---
    def add_listener(self, callback):
        """Register a no-arg callback fired whenever the library changes."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def _changed(self):
        self.save()
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                pass

    # ------------------------------------------------------------ profiles ---
    def list_profiles(self):
        """Global first, then the rest in insertion order."""
        return [GLOBAL_PROFILE] + [n for n in self.data["profiles"] if n != GLOBAL_PROFILE]

    def get_profile(self, name):
        return self.data["profiles"].get(name)

    def add_profile(self, name, window_match=None):
        name = (name or "").strip()
        if not name or name in self.data["profiles"]:
            return False
        self.data["profiles"][name] = {
            "window_match": list(window_match or []),
            "recordings": {},
        }
        self._changed()
        return True

    def rename_profile(self, old, new):
        new = (new or "").strip()
        if old == GLOBAL_PROFILE or old not in self.data["profiles"]:
            return False
        if not new or new in self.data["profiles"]:
            return False
        profiles = self.data["profiles"]
        self.data["profiles"] = {(new if k == old else k): v for k, v in profiles.items()}
        if self.data["active_profile"] == old:
            self.data["active_profile"] = new
        self._changed()
        return True

    def delete_profile(self, name):
        if name == GLOBAL_PROFILE or name not in self.data["profiles"]:
            return False
        del self.data["profiles"][name]
        if self.data["active_profile"] == name:
            self.data["active_profile"] = GLOBAL_PROFILE
        self._changed()
        return True

    def set_window_match(self, name, patterns):
        prof = self.get_profile(name)
        if prof is None:
            return False
        prof["window_match"] = [p.strip() for p in patterns if p.strip()]
        self._changed()
        return True

    # ---------------------------------------------------------- recordings ---
    def add_recording(self, profile, name, events, settings=None, hotkey=None):
        prof = self.get_profile(profile)
        if prof is None:
            return None
        rid = new_id()
        prof["recordings"][rid] = {
            "name": (name or "Untitled").strip() or "Untitled",
            "events": copy.deepcopy(events) if events else {"events": []},
            "settings": copy.deepcopy(settings) if settings else None,
            "hotkey": list(hotkey or []),
            "created": time(),
        }
        self._changed()
        return rid

    def get_recording(self, profile, rid):
        prof = self.get_profile(profile)
        if prof is None:
            return None
        return prof["recordings"].get(rid)

    def find_recording(self, rid):
        """Return (profile, recording) for a recording id across all profiles."""
        for pname, prof in self.data["profiles"].items():
            if rid in prof["recordings"]:
                return pname, prof["recordings"][rid]
        return None, None

    def rename_recording(self, profile, rid, new_name):
        rec = self.get_recording(profile, rid)
        if rec is None:
            return False
        rec["name"] = (new_name or "Untitled").strip() or "Untitled"
        self._changed()
        return True

    def delete_recording(self, profile, rid):
        prof = self.get_profile(profile)
        if prof is None or rid not in prof["recordings"]:
            return False
        del prof["recordings"][rid]
        self._changed()
        return True

    def move_recording(self, src_profile, rid, dst_profile):
        src = self.get_profile(src_profile)
        dst = self.get_profile(dst_profile)
        if not src or not dst or rid not in src["recordings"]:
            return False
        dst["recordings"][rid] = src["recordings"].pop(rid)
        self._changed()
        return True

    def set_recording_hotkey(self, profile, rid, hotkey):
        rec = self.get_recording(profile, rid)
        if rec is None:
            return False
        rec["hotkey"] = list(hotkey or [])
        self._changed()
        return True

    # ------------------------------------------------------- active profile ---
    def get_active_profile(self):
        return self.data.get("active_profile", GLOBAL_PROFILE)

    def set_active_profile(self, name):
        if name in self.data["profiles"] and name != self.data.get("active_profile"):
            self.data["active_profile"] = name
            self._changed()
            return True
        return False

    def cycle_active_profile(self):
        order = self.list_profiles()
        if len(order) < 2:
            return self.get_active_profile()
        cur = self.get_active_profile()
        idx = order.index(cur) if cur in order else 0
        nxt = order[(idx + 1) % len(order)]
        self.set_active_profile(nxt)
        return nxt

    # ---------------------------------------------------------- auto switch ---
    def get_auto_switch(self):
        return bool(self.data.get("auto_switch", False))

    def set_auto_switch(self, value):
        self.data["auto_switch"] = bool(value)
        self._changed()

    def toggle_auto_switch(self):
        self.set_auto_switch(not self.get_auto_switch())
        return self.get_auto_switch()

    # ------------------------------------------------------- window matching ---
    def match_window(self, title, process=None):
        """
        Return the profile name whose window_match patterns match the given
        window title or process name (case-insensitive substring). Global is
        never matched here. Returns None when nothing matches.
        """
        hay = " ".join(str(x) for x in (title or "", process or "")).lower()
        for name in self.list_profiles():
            if name == GLOBAL_PROFILE:
                continue
            prof = self.data["profiles"][name]
            for pat in prof.get("window_match", []):
                pat = (pat or "").strip().lower()
                if pat and pat in hay:
                    return name
        return None

    # --------------------------------------------------- active resolution ---
    def active_recordings(self):
        """
        Recordings that are 'live' right now: every Global recording plus the
        active profile's recordings. Satisfies 'Default Global profile includes
        macros for all profiles'.
        """
        out = []
        seen = set()
        active = self.get_active_profile()
        order = [GLOBAL_PROFILE, active] if active != GLOBAL_PROFILE else [GLOBAL_PROFILE]
        for pname in order:
            prof = self.get_profile(pname)
            if not prof:
                continue
            for rid, rec in prof["recordings"].items():
                if rid in seen:
                    continue
                seen.add(rid)
                out.append({
                    "profile": pname,
                    "id": rid,
                    "name": rec["name"],
                    "hotkey": rec.get("hotkey", []),
                    "events": rec.get("events", {"events": []}),
                    "settings": rec.get("settings"),
                })
        return out

    def active_hotkey_bindings(self):
        """Active recordings that have a hotkey assigned."""
        return [r for r in self.active_recordings() if r.get("hotkey")]

    # ------------------------------------------------------------ meta-binds ---
    def list_meta_binds(self):
        return self.data.get("meta_binds", {})

    def add_meta_bind(self, action, arg=None, hotkey=None):
        if action not in META_ACTIONS:
            return None
        bid = new_id()
        self.data["meta_binds"][bid] = {
            "action": action,
            "arg": arg,
            "hotkey": list(hotkey or []),
        }
        self._changed()
        return bid

    def update_meta_bind(self, bid, action=None, arg=None, hotkey=None):
        mb = self.data["meta_binds"].get(bid)
        if mb is None:
            return False
        if action is not None:
            mb["action"] = action
        if arg is not None:
            mb["arg"] = arg
        if hotkey is not None:
            mb["hotkey"] = list(hotkey)
        self._changed()
        return True

    def delete_meta_bind(self, bid):
        if bid in self.data.get("meta_binds", {}):
            del self.data["meta_binds"][bid]
            self._changed()
            return True
        return False
