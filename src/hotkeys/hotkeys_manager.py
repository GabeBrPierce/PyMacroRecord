from tkinter import messagebox

from pynput import keyboard, mouse

from utils.get_key_pressed import (
    getKeyPressed,
    normalize_key,
    mouse_hotkey_token,
    display_key,
)
from utils.keys import vk_nb


class HotkeysManager:
    def __init__(self, main_app):
        self.keyboard_listener = keyboard.Listener(
            on_press=self.__on_press,
            on_release=self.__on_release,
            win32_event_filter=self.__win32_event_filter,
        )
        self.main_app = main_app
        self.settings = main_app.settings
        self.hotkeys = []
        self.hotkey_visible = []
        self.hotkey_detection = set()
        self._triggered_hotkeys = set()
        self.macro = main_app.macro
        self.hotkey_button = None
        self.type_of_hotkey = None
        self.entry_to_change = None
        self.changeKey = False
        self.index_to_change = 0
        self.keyboard_listener.start()

        # Also listen for thumb / side mouse buttons so they can act as hotkeys.
        self.mouse_listener = mouse.Listener(on_click=self.__on_mouse_click)
        self.mouse_listener.start()

    def enable_hot_key_detection(self, type_of_hotkey, entry_to_change, index):
        self.hotkey_button = entry_to_change
        self.type_of_hotkey = type_of_hotkey
        self.index_to_change = index
        self.changeKey = True
        self.entry_to_change = entry_to_change
        self.entry_to_change.configure(text=self.main_app.text_content["options_menu"]["settings_menu"]["hotkeys_settings"]["please_key_text"])

    def clear_hot_key(self, type, entry_to_change):
        self.settings.change_settings("Hotkeys", type, None, [])
        entry_to_change.configure(text="")

    def __win32_event_filter(self, msg, data):
        """Detect if key is pressed by real keyboard or pynput"""
        if data.flags == 0x10:
            if self.macro.playback and not self.macro.record:
                return False
            else:
                return True

    # ------------------------------------------------------------ capture ---
    def __capture(self, token, display, finalizing):
        """Add a pressed key/button to the hotkey being assigned (built-in
        hotkeys settings window). When 'finalizing' (a non-modifier key or a
        mouse button), validate and persist the combo."""
        if token not in self.hotkeys:
            self.hotkeys.append(token)
            self.hotkey_visible.append(display)
        self.hotkey_button.configure(text=self.hotkey_visible)
        if not finalizing:
            return
        userSettings = self.settings.settings_dict
        if (
            self.type_of_hotkey == "Record_Start"
            and userSettings["Hotkeys"]["Playback_Start"] == self.hotkeys
            or self.type_of_hotkey == "Playback_Start"
            and userSettings["Hotkeys"]["Record_Start"] == self.hotkeys
        ):
            messagebox.showerror(
                self.main_app.text_content["global"]["error"],
                self.main_app.text_content["options_menu"]["settings_menu"]["hotkeys_settings"]["error_hotkeys"],
            )
            self.entry_to_change.configure(text=self.main_app.text_content["options_menu"]["settings_menu"]["hotkeys_settings"]["please_key_text"])
            self.hotkeys = []
            self.hotkey_visible = []
            return
        self.settings.change_settings("Hotkeys", self.type_of_hotkey, None, self.hotkeys)
        self.changeKey = False
        self.hotkeys = []
        self.hotkey_visible = []

    # --------------------------------------------------------- keyboard in ---
    def __on_press(self, key):
        if self.changeKey:
            keyPressed = getKeyPressed(self.keyboard_listener, key)
            if keyPressed is None:
                return
            keyPressed = normalize_key(keyPressed)
            if ">" in keyPressed:
                try:
                    keyPressed = vk_nb[keyPressed]
                except KeyError:
                    pass
            finalizing = all(
                kw not in keyPressed for kw in ["ctrl", "alt", "shift", "cmd"]
            )
            self.__capture(keyPressed, display_key(keyPressed), finalizing)
            return

        if self.main_app.prevent_record:
            return

        keyPressed = getKeyPressed(self.keyboard_listener, key)
        if keyPressed is None:
            return
        if ">" in keyPressed:
            try:
                keyPressed = vk_nb[keyPressed]
            except KeyError:
                pass
        self.hotkey_detection.add(normalize_key(keyPressed))
        self.__evaluate_triggers()

    def __on_release(self, key):
        key_released = getKeyPressed(self.keyboard_listener, key)
        if key_released is not None:
            self.hotkey_detection.discard(normalize_key(key_released))
        self._triggered_hotkeys.clear()

    # ------------------------------------------------------------ mouse in ---
    def __on_mouse_click(self, x, y, button, pressed):
        token = mouse_hotkey_token(button)
        if token is None:
            return  # only thumb / side buttons are hotkey-eligible

        if self.changeKey:
            if pressed:
                # a mouse button always finalizes the combo
                self.__capture(token, display_key(token), True)
            return

        if self.main_app.prevent_record:
            return

        if pressed:
            self.hotkey_detection.add(token)
            self.__evaluate_triggers()
        else:
            self.hotkey_detection.discard(token)
            self._triggered_hotkeys.clear()

    # ------------------------------------------------------- trigger logic ---
    def __evaluate_triggers(self):
        userSettings = self.settings.settings_dict
        hotkeys = userSettings["Hotkeys"]

        if (
            "Record_Start" not in self._triggered_hotkeys
            and self.__is_hotkey_triggered(hotkeys["Record_Start"], self.hotkey_detection)
            and not self.macro.record
            and not self.macro.playback
        ):
            self._triggered_hotkeys.add("Record_Start")
            self.macro.start_record(True)

        elif (
            "Record_Stop" not in self._triggered_hotkeys
            and self.__is_hotkey_triggered(hotkeys["Record_Stop"], self.hotkey_detection)
            and self.macro.record
            and not self.macro.playback
        ):
            self._triggered_hotkeys.add("Record_Stop")
            self.macro.stop_record()

        elif (
            "Playback_Start" not in self._triggered_hotkeys
            and self.__is_hotkey_triggered(hotkeys["Playback_Start"], self.hotkey_detection)
            and not self.macro.record
            and not self.macro.playback
            and self.main_app.macro_recorded
        ):
            self._triggered_hotkeys.add("Playback_Start")
            self.macro.start_playback()

        elif (
            "Playback_Stop" not in self._triggered_hotkeys
            and self.__is_hotkey_triggered(hotkeys["Playback_Stop"], self.hotkey_detection)
            and not self.macro.record
            and self.macro.playback
        ):
            self._triggered_hotkeys.add("Playback_Stop")
            self.macro.stop_playback(True)

        self.__check_dynamic_bindings()

    def __check_dynamic_bindings(self):
        """Trigger meta-binds (always active) and active-profile + Global
        recording hotkeys. Meta-binds are checked even during playback so that
        panic / stop-all remain usable; recording hotkeys only start playback
        when idle."""
        library = getattr(self.main_app, "library", None)
        if library is None:
            return
        detected = self.hotkey_detection

        meta_exec = getattr(self.main_app, "meta_executor", None)
        if meta_exec is not None:
            for bid, mb in library.list_meta_binds().items():
                token = "meta:" + bid
                if token in self._triggered_hotkeys:
                    continue
                if self.__is_hotkey_triggered(mb.get("hotkey"), detected):
                    self._triggered_hotkeys.add(token)
                    meta_exec.run(mb.get("action"), mb.get("arg"))

        if self.macro.record or self.macro.playback:
            return
        for binding in library.active_hotkey_bindings():
            token = "rec:" + binding["id"]
            if token in self._triggered_hotkeys:
                continue
            if self.__is_hotkey_triggered(binding.get("hotkey"), detected):
                self._triggered_hotkeys.add(token)
                rec = {"events": binding["events"], "settings": binding.get("settings")}
                self.macro.play_library_recording(rec)
                break

    def __is_hotkey_triggered(self, hotkey_config, detected_keys):
        if not hotkey_config or not isinstance(hotkey_config, list):
            return False
        return {normalize_key(k) for k in hotkey_config}.issubset(detected_keys)
