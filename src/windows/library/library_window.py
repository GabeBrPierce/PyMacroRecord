"""The Macro Library manager window.

Shows every profile and its recordings in a tree, lets you play a recording
outright, save the current recording into a profile, assign per-recording
hotkeys, manage profiles, configure window-match rules for automatic profile
switching, and open the meta-binds editor.
"""

from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, X, BooleanVar, StringVar, Toplevel
from tkinter import messagebox, simpledialog
from tkinter.ttk import Button, Checkbutton, Frame, Label, Treeview

from utils.library import GLOBAL_PROFILE
from utils.get_key_pressed import display_keys
from utils.window_watcher import get_active_window, platform_supported
from windows.library.hotkey_capture import capture_hotkey
from windows.library.meta_binds_window import MetaBindsWindow


def _fmt_keys(keys):
    return display_keys(keys)


class LibraryWindow(Toplevel):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.library = main_app.library
        self.title("Macro Library")
        self.geometry("640x460")
        self.attributes("-topmost", 1)

        # --- top bar: active profile + auto switch -----------------------
        top = Frame(self, padding=(10, 8))
        top.pack(side=TOP, fill=X)
        self.active_var = StringVar(value=self._active_text())
        Label(top, textvariable=self.active_var, font=("Segoe UI", 11, "bold")).pack(side=LEFT)
        self.auto_var = BooleanVar(value=self.library.get_auto_switch())
        chk = Checkbutton(top, text="Auto-switch by window", variable=self.auto_var,
                          command=self._toggle_auto)
        chk.pack(side=RIGHT)
        if not platform_supported():
            chk.configure(state="disabled")

        # --- tree --------------------------------------------------------
        mid = Frame(self)
        mid.pack(side=TOP, fill=BOTH, expand=True, padx=10)
        self.tree = Treeview(mid, columns=("hotkey",), show="tree headings")
        self.tree.heading("#0", text="Profiles & Recordings")
        self.tree.heading("hotkey", text="Hotkey / Window rules")
        self.tree.column("#0", width=380)
        self.tree.column("hotkey", width=210)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)
        self.tree.bind("<Double-1>", lambda e: self._play())

        # --- buttons -----------------------------------------------------
        bar = Frame(self, padding=(10, 6))
        bar.pack(side=BOTTOM, fill=X)

        row1 = Frame(bar)
        row1.pack(side=TOP, fill=X, pady=2)
        Button(row1, text="Play", command=self._play).pack(side=LEFT, padx=3)
        Button(row1, text="Save current recording", command=self._save_current).pack(side=LEFT, padx=3)
        Button(row1, text="Set hotkey", command=self._set_rec_hotkey).pack(side=LEFT, padx=3)
        Button(row1, text="Rename", command=self._rename_recording).pack(side=LEFT, padx=3)
        Button(row1, text="Move to...", command=self._move_recording).pack(side=LEFT, padx=3)
        Button(row1, text="Delete", command=self._delete_recording).pack(side=LEFT, padx=3)

        row2 = Frame(bar)
        row2.pack(side=TOP, fill=X, pady=2)
        Button(row2, text="New profile", command=self._new_profile).pack(side=LEFT, padx=3)
        Button(row2, text="Rename profile", command=self._rename_profile).pack(side=LEFT, padx=3)
        Button(row2, text="Delete profile", command=self._delete_profile).pack(side=LEFT, padx=3)
        Button(row2, text="Set active", command=self._set_active).pack(side=LEFT, padx=3)
        Button(row2, text="Window rules...", command=self._window_rules).pack(side=LEFT, padx=3)

        row3 = Frame(bar)
        row3.pack(side=TOP, fill=X, pady=2)
        Button(row3, text="Meta-binds...", command=lambda: MetaBindsWindow(self, self.main_app)).pack(side=LEFT, padx=3)
        Button(row3, text="Close", command=self.destroy).pack(side=RIGHT, padx=3)

        self._index = {}     # tree iid -> ("profile", name) or ("rec", profile, rid)
        self.library.add_listener(self._on_library_changed)
        self.refresh()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ------------------------------------------------------------ helpers ---
    def _active_text(self):
        return "Active profile: %s" % self.library.get_active_profile()

    def _on_library_changed(self):
        # called from any thread; marshal to Tk thread
        try:
            self.after(0, self.refresh)
        except Exception:
            pass

    def refresh(self):
        if not self.tree.winfo_exists():
            return
        self.tree.delete(*self.tree.get_children())
        self._index = {}
        active = self.library.get_active_profile()
        for pname in self.library.list_profiles():
            prof = self.library.get_profile(pname)
            label = pname + ("  (active)" if pname == active else "")
            if pname != GLOBAL_PROFILE and prof.get("window_match"):
                rules = ", ".join(prof["window_match"])
            else:
                rules = ""
            piid = self.tree.insert("", END, text=label, values=(rules,), open=True)
            self._index[piid] = ("profile", pname)
            for rid, rec in prof["recordings"].items():
                riid = self.tree.insert(piid, END, text="   " + rec["name"],
                                        values=(_fmt_keys(rec.get("hotkey")),))
                self._index[riid] = ("rec", pname, rid)
        self.active_var.set(self._active_text())
        self.auto_var.set(self.library.get_auto_switch())

    def _selection(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._index.get(sel[0])

    def _selected_profile_name(self):
        info = self._selection()
        if not info:
            return None
        if info[0] == "profile":
            return info[1]
        return info[1]   # rec -> its profile

    # ------------------------------------------------------------ actions ---
    def _toggle_auto(self):
        self.library.set_auto_switch(self.auto_var.get())
        self.main_app.refresh_auto_switch_var()

    def _play(self):
        info = self._selection()
        if not info or info[0] != "rec":
            return
        _, pname, rid = info
        rec = self.library.get_recording(pname, rid)
        if rec is None:
            return
        if self.main_app.macro.playback or self.main_app.macro.record:
            messagebox.showinfo("Macro Library", "Stop the current playback/record first.", parent=self)
            return
        self.main_app.macro.play_library_recording(rec)

    def _save_current(self):
        app = self.main_app
        if not getattr(app, "macro_recorded", False) or not app.macro.macro_events.get("events"):
            messagebox.showinfo("Macro Library",
                                "There is no current recording to save. Record a macro first.",
                                parent=self)
            return
        pname = self._selected_profile_name() or GLOBAL_PROFILE
        name = simpledialog.askstring("Save recording",
                                      "Name for this recording (profile: %s):" % pname,
                                      parent=self)
        if not name:
            return
        settings = {
            "Playback": app.settings.settings_dict.get("Playback"),
        }
        self.library.add_recording(pname, name, app.macro.macro_events, settings=settings)
        self.refresh()

    def _set_rec_hotkey(self):
        info = self._selection()
        if not info or info[0] != "rec":
            messagebox.showinfo("Macro Library", "Select a recording first.", parent=self)
            return
        _, pname, rid = info
        rec = self.library.get_recording(pname, rid)
        result = capture_hotkey(self, self.main_app, initial=rec.get("hotkey", []),
                                title="Hotkey for '%s'" % rec["name"])
        if result is not None:
            self.library.set_recording_hotkey(pname, rid, result)
            self.refresh()

    def _rename_recording(self):
        info = self._selection()
        if not info or info[0] != "rec":
            return
        _, pname, rid = info
        rec = self.library.get_recording(pname, rid)
        name = simpledialog.askstring("Rename", "New name:", initialvalue=rec["name"], parent=self)
        if name:
            self.library.rename_recording(pname, rid, name)
            self.refresh()

    def _move_recording(self):
        info = self._selection()
        if not info or info[0] != "rec":
            return
        _, pname, rid = info
        others = [p for p in self.library.list_profiles() if p != pname]
        if not others:
            return
        dst = _choose(self, "Move recording", "Move to profile:", others)
        if dst:
            self.library.move_recording(pname, rid, dst)
            self.refresh()

    def _delete_recording(self):
        info = self._selection()
        if not info or info[0] != "rec":
            return
        _, pname, rid = info
        rec = self.library.get_recording(pname, rid)
        if messagebox.askyesno("Delete", "Delete recording '%s'?" % rec["name"], parent=self):
            self.library.delete_recording(pname, rid)
            self.refresh()

    def _new_profile(self):
        name = simpledialog.askstring("New profile", "Profile name:", parent=self)
        if not name:
            return
        if not self.library.add_profile(name):
            messagebox.showerror("New profile", "A profile with that name already exists.", parent=self)
            return
        self.refresh()

    def _rename_profile(self):
        pname = self._selected_profile_name()
        if not pname or pname == GLOBAL_PROFILE:
            messagebox.showinfo("Rename profile", "Select a non-Global profile.", parent=self)
            return
        name = simpledialog.askstring("Rename profile", "New name:", initialvalue=pname, parent=self)
        if name and not self.library.rename_profile(pname, name):
            messagebox.showerror("Rename profile", "Could not rename (name in use?).", parent=self)
        self.refresh()

    def _delete_profile(self):
        pname = self._selected_profile_name()
        if not pname or pname == GLOBAL_PROFILE:
            messagebox.showinfo("Delete profile", "The Global profile cannot be deleted.", parent=self)
            return
        if messagebox.askyesno("Delete profile",
                               "Delete profile '%s' and all its recordings?" % pname, parent=self):
            self.library.delete_profile(pname)
            self.refresh()

    def _set_active(self):
        pname = self._selected_profile_name()
        if pname:
            self.library.set_active_profile(pname)
            self.refresh()

    def _window_rules(self):
        pname = self._selected_profile_name()
        if not pname or pname == GLOBAL_PROFILE:
            messagebox.showinfo("Window rules",
                                "Pick a non-Global profile. Window rules decide which "
                                "profile auto-activates for a given window.", parent=self)
            return
        WindowRulesDialog(self, self.main_app, pname, on_done=self.refresh)

    def _close(self):
        try:
            if self._on_library_changed in self.library._listeners:
                self.library._listeners.remove(self._on_library_changed)
        except Exception:
            pass
        self.destroy()


def _choose(parent, title, prompt, options):
    """Tiny modal single-choice picker; returns the chosen string or None."""
    dlg = Toplevel(parent)
    dlg.title(title)
    dlg.attributes("-topmost", 1)
    dlg.resizable(False, False)
    Label(dlg, text=prompt, padding=10).pack()
    var = StringVar(value=options[0])
    from tkinter.ttk import Combobox
    cb = Combobox(dlg, textvariable=var, values=options, state="readonly", width=28)
    cb.pack(padx=12, pady=6)
    result = {"value": None}

    def ok():
        result["value"] = var.get()
        dlg.destroy()

    btns = Frame(dlg)
    btns.pack(pady=10)
    Button(btns, text="OK", command=ok).pack(side=LEFT, padx=6)
    Button(btns, text="Cancel", command=dlg.destroy).pack(side=LEFT, padx=6)
    dlg.grab_set()
    dlg.wait_window()
    return result["value"]


class WindowRulesDialog(Toplevel):
    """Edit the window-match patterns for a profile (one per line)."""

    def __init__(self, parent, main_app, profile, on_done=None):
        super().__init__(parent)
        self.main_app = main_app
        self.library = main_app.library
        self.profile = profile
        self.on_done = on_done
        self.title("Window rules - %s" % profile)
        self.geometry("440x320")
        self.attributes("-topmost", 1)

        Label(self, text="Activate this profile when the focused window title or\n"
                         "process matches any of these (one substring per line):",
              padding=8, justify=LEFT).pack(side=TOP, fill=X)

        from tkinter import Text
        self.text = Text(self, height=8, width=44)
        self.text.pack(side=TOP, fill=BOTH, expand=True, padx=10)
        prof = self.library.get_profile(profile)
        self.text.insert("1.0", "\n".join(prof.get("window_match", [])))

        btns = Frame(self, padding=8)
        btns.pack(side=BOTTOM, fill=X)
        Button(btns, text="Capture current window", command=self._capture).pack(side=LEFT, padx=3)
        Button(btns, text="Save", command=self._save).pack(side=LEFT, padx=3)
        Button(btns, text="Cancel", command=self.destroy).pack(side=RIGHT, padx=3)
        self.grab_set()

    def _capture(self):
        title, process = get_active_window()
        hint = process or title
        if hint:
            cur = self.text.get("1.0", END).strip()
            self.text.delete("1.0", END)
            self.text.insert("1.0", (cur + "\n" + hint).strip() if cur else hint)
        else:
            messagebox.showinfo("Window rules", "Could not read the active window on this platform.", parent=self)

    def _save(self):
        lines = [ln for ln in self.text.get("1.0", END).splitlines()]
        self.library.set_window_match(self.profile, lines)
        if self.on_done:
            self.on_done()
        self.destroy()
