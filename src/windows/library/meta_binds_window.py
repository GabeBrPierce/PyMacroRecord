"""Editor for meta-binds: hotkeys that trigger system / app operations
(switch profile, panic, lock computer, ...) instead of replaying a macro."""

from tkinter import BOTH, BOTTOM, END, LEFT, RIGHT, TOP, X, StringVar, Toplevel
from tkinter import messagebox
from tkinter.ttk import Button, Combobox, Frame, Label, Treeview

from utils.library import META_ACTIONS, GLOBAL_PROFILE
from utils.get_key_pressed import display_keys
from windows.library.hotkey_capture import capture_hotkey


def _fmt_keys(keys):
    return display_keys(keys) or "(unbound)"


class MetaBindsWindow(Toplevel):
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.library = main_app.library
        self.title("Meta-Binds")
        self.geometry("560x360")
        self.attributes("-topmost", 1)

        Label(self, text="Meta-binds run an action when their hotkey is pressed, "
                         "regardless of the active profile.", padding=8).pack(side=TOP, fill=X)

        tree_frame = Frame(self)
        tree_frame.pack(side=TOP, fill=BOTH, expand=True, padx=8)
        self.tree = Treeview(tree_frame, columns=("arg", "hotkey"), show="tree headings", height=8)
        self.tree.heading("#0", text="Action")
        self.tree.heading("arg", text="Target")
        self.tree.heading("hotkey", text="Hotkey")
        self.tree.column("#0", width=220)
        self.tree.column("arg", width=160)
        self.tree.column("hotkey", width=140)
        self.tree.pack(side=LEFT, fill=BOTH, expand=True)

        btns = Frame(self)
        btns.pack(side=BOTTOM, fill=X, pady=8, padx=8)
        Button(btns, text="Add", command=self._add).pack(side=LEFT, padx=4)
        Button(btns, text="Edit", command=self._edit).pack(side=LEFT, padx=4)
        Button(btns, text="Delete", command=self._delete).pack(side=LEFT, padx=4)
        Button(btns, text="Close", command=self.destroy).pack(side=RIGHT, padx=4)

        self._index = {}
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._index = {}
        for bid, mb in self.library.list_meta_binds().items():
            action = mb.get("action")
            label = META_ACTIONS.get(action, {}).get("label", action)
            arg = mb.get("arg") or ""
            iid = self.tree.insert("", END, text=label, values=(arg, _fmt_keys(mb.get("hotkey"))))
            self._index[iid] = bid

    def _selected_bid(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._index.get(sel[0])

    def _add(self):
        MetaBindEditor(self, self.main_app, on_done=self.refresh)

    def _edit(self):
        bid = self._selected_bid()
        if bid is None:
            return
        MetaBindEditor(self, self.main_app, bid=bid, on_done=self.refresh)

    def _delete(self):
        bid = self._selected_bid()
        if bid is None:
            return
        if messagebox.askyesno("Meta-Binds", "Delete this meta-bind?", parent=self):
            self.library.delete_meta_bind(bid)
            self.refresh()


class MetaBindEditor(Toplevel):
    def __init__(self, parent, main_app, bid=None, on_done=None):
        super().__init__(parent)
        self.main_app = main_app
        self.library = main_app.library
        self.bid = bid
        self.on_done = on_done
        self.title("Meta-bind")
        self.geometry("420x230")
        self.attributes("-topmost", 1)

        existing = self.library.list_meta_binds().get(bid, {}) if bid else {}
        self._hotkey = list(existing.get("hotkey", []))

        # Action picker
        self._action_keys = list(META_ACTIONS.keys())
        self._labels = [META_ACTIONS[k]["label"] for k in self._action_keys]
        cur_action = existing.get("action", self._action_keys[0])

        form = Frame(self, padding=12)
        form.pack(fill=BOTH, expand=True)

        Label(form, text="Action:").grid(row=0, column=0, sticky="w", pady=6)
        self.action_var = StringVar(value=META_ACTIONS.get(cur_action, {}).get("label", self._labels[0]))
        self.action_cb = Combobox(form, textvariable=self.action_var, values=self._labels,
                                  state="readonly", width=28)
        self.action_cb.grid(row=0, column=1, sticky="w")
        self.action_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_arg())

        Label(form, text="Target:").grid(row=1, column=0, sticky="w", pady=6)
        self.arg_var = StringVar(value=existing.get("arg") or "")
        self.arg_cb = Combobox(form, textvariable=self.arg_var, values=[], width=28)
        self.arg_cb.grid(row=1, column=1, sticky="w")

        Label(form, text="Hotkey:").grid(row=2, column=0, sticky="w", pady=6)
        self.hotkey_lbl = Label(form, text=_fmt_keys(self._hotkey))
        self.hotkey_lbl.grid(row=2, column=1, sticky="w")
        Button(form, text="Set hotkey...", command=self._set_hotkey).grid(row=3, column=1, sticky="w", pady=4)

        btns = Frame(self)
        btns.pack(side=BOTTOM, fill=X, pady=10, padx=10)
        Button(btns, text="Save", command=self._save).pack(side=LEFT, padx=4)
        Button(btns, text="Cancel", command=self.destroy).pack(side=RIGHT, padx=4)

        self._refresh_arg()
        self.grab_set()

    def _current_action_key(self):
        try:
            return self._action_keys[self._labels.index(self.action_var.get())]
        except ValueError:
            return self._action_keys[0]

    def _refresh_arg(self):
        action = self._current_action_key()
        needs = META_ACTIONS[action]["needs_arg"]
        if needs == "profile":
            vals = [p for p in self.library.list_profiles() if p != GLOBAL_PROFILE]
            self.arg_cb.configure(values=vals, state="readonly")
        elif needs == "recording":
            vals, self._rec_map = [], {}
            for pname in self.library.list_profiles():
                prof = self.library.get_profile(pname)
                for rid, rec in prof["recordings"].items():
                    label = "%s / %s" % (pname, rec["name"])
                    vals.append(label)
                    self._rec_map[label] = rid
            self.arg_cb.configure(values=vals, state="readonly")
        else:
            self.arg_var.set("")
            self.arg_cb.configure(values=[], state="disabled")

    def _set_hotkey(self):
        result = capture_hotkey(self, self.main_app, initial=self._hotkey, title="Meta-bind hotkey")
        if result is not None:
            self._hotkey = result
            self.hotkey_lbl.configure(text=_fmt_keys(self._hotkey))

    def _save(self):
        action = self._current_action_key()
        needs = META_ACTIONS[action]["needs_arg"]
        arg = None
        if needs == "profile":
            arg = self.arg_var.get() or None
            if not arg:
                messagebox.showerror("Meta-bind", "Pick a target profile.", parent=self)
                return
        elif needs == "recording":
            label = self.arg_var.get()
            arg = getattr(self, "_rec_map", {}).get(label)
            if not arg:
                messagebox.showerror("Meta-bind", "Pick a target recording.", parent=self)
                return
        if self.bid:
            self.library.update_meta_bind(self.bid, action=action, arg=arg, hotkey=self._hotkey)
        else:
            self.library.add_meta_bind(action, arg=arg, hotkey=self._hotkey)
        if self.on_done:
            self.on_done()
        self.destroy()
