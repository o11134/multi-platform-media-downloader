from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk

from core.preferences import AppPreferences


TOKENS = {
    "surface": "#131313",
    "surface_container_low": "#1b1b1c",
    "surface_container_high": "#2a2a2a",
    "surface_container_highest": "#353535",
    "surface_container_lowest": "#0e0e0e",
    "surface_bright": "#393939",
    "on_surface": "#e5e2e1",
    "on_surface_variant": "#ebbbb4",
    "muted": "#474747",
    "primary_container": "#ff5540",
    "red": "#FF0000",
}


class SettingsView(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        preferences: AppPreferences,
        on_browse: Callable[[], None],
        on_browse_cookies: Callable[[], None],
        on_apply: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self._on_browse = on_browse
        self._on_browse_cookies = on_browse_cookies
        self._on_apply = on_apply

        self.quality_var = ctk.StringVar(value=preferences.quality)
        self.format_var = ctk.StringVar(value=preferences.file_format)
        self.parallel_var = ctk.StringVar(value=str(preferences.parallel_downloads))
        self.output_dir_var = ctk.StringVar(value=preferences.last_output_dir)
        self.auto_subfolder_var = ctk.BooleanVar(value=preferences.auto_subfolder)
        self.sound_var = ctk.BooleanVar(value=preferences.sound_enabled)
        self.dark_mode_var = ctk.BooleanVar(value=preferences.appearance_mode != "light")
        self.scope_var = ctk.StringVar(value=preferences.scope_mode)
        self.max_items_var = ctk.StringVar(value=str(preferences.max_items))
        self.video_only_var = ctk.BooleanVar(value=preferences.video_only)
        self.cookies_mode_var = ctk.StringVar(value=preferences.cookies_mode)
        self.cookies_browser_var = ctk.StringVar(value=preferences.cookies_browser)
        self.cookies_file_var = ctk.StringVar(value=preferences.cookies_file)

        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self,
            text="SETTINGS",
            text_color=TOKENS["muted"],
            font=("Inter", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=6, pady=(2, 2), sticky="w")

        ctk.CTkLabel(
            self,
            text="Engine Configuration",
            text_color=TOKENS["on_surface"],
            font=("Inter", 34, "bold"),
            anchor="w",
        ).grid(row=1, column=0, padx=6, pady=(0, 16), sticky="w")

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=2, column=0, sticky="ew")
        top.grid_columnconfigure((0, 1), weight=1)

        left = ctk.CTkFrame(top, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        left.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        accent = ctk.CTkFrame(left, fg_color=TOKENS["red"], width=4, corner_radius=2)
        accent.grid(row=0, column=0, rowspan=10, sticky="nsw")

        ctk.CTkLabel(left, text="DOWNLOAD QUALITY", text_color=TOKENS["on_surface_variant"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, padx=(12, 12), pady=(12, 6), sticky="w"
        )

        ctk.CTkLabel(left, text="Preferred Quality", text_color=TOKENS["on_surface"], font=("Inter", 12)).grid(
            row=1, column=0, padx=(12, 12), sticky="w"
        )
        self.quality_menu = ctk.CTkOptionMenu(
            left,
            values=["1080p", "720p", "480p", "360p", "Audio Only"],
            variable=self.quality_var,
            fg_color=TOKENS["surface_container_lowest"],
            button_color=TOKENS["surface_container_highest"],
            dropdown_fg_color=TOKENS["surface_container_low"],
            corner_radius=8,
        )
        self.quality_menu.grid(row=2, column=0, padx=12, pady=(4, 10), sticky="ew")

        ctk.CTkLabel(left, text="Video Format", text_color=TOKENS["on_surface"], font=("Inter", 12)).grid(
            row=3, column=0, padx=(12, 12), sticky="w"
        )
        self.format_menu = ctk.CTkOptionMenu(
            left,
            values=["MP4", "MKV", "MP3", "M4A"],
            variable=self.format_var,
            fg_color=TOKENS["surface_container_lowest"],
            button_color=TOKENS["surface_container_highest"],
            dropdown_fg_color=TOKENS["surface_container_low"],
            corner_radius=8,
        )
        self.format_menu.grid(row=4, column=0, padx=12, pady=(4, 14), sticky="ew")

        right = ctk.CTkFrame(top, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        right.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(right, text="ENGINE PERFORMANCE", text_color=TOKENS["on_surface_variant"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )
        ctk.CTkLabel(right, text="Parallel downloads", text_color=TOKENS["on_surface"], font=("Inter", 12)).grid(
            row=1, column=0, padx=12, sticky="w"
        )
        self.parallel_entry = ctk.CTkEntry(
            right,
            textvariable=self.parallel_var,
            fg_color=TOKENS["surface_container_lowest"],
            border_width=0,
            corner_radius=8,
            width=80,
        )
        self.parallel_entry.grid(row=2, column=0, padx=12, pady=(4, 6), sticky="w")

        ctk.CTkLabel(
            right,
            text="1-3 Slots",
            fg_color=TOKENS["surface_container_high"],
            text_color=TOKENS["on_surface_variant"],
            corner_radius=8,
            padx=8,
            pady=3,
            font=("Inter", 10, "bold"),
        ).grid(row=2, column=0, padx=(100, 0), pady=(4, 6), sticky="w")

        info = ctk.CTkFrame(right, fg_color=TOKENS["surface_container_lowest"], corner_radius=8)
        info.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        ctk.CTkLabel(info, text="ℹ", text_color="#f5a623", font=("Inter", 14, "bold")).grid(row=0, column=0, padx=(8, 4), pady=8)
        ctk.CTkLabel(
            info,
            text="Higher parallelism increases bandwidth usage and CPU load.",
            text_color=TOKENS["on_surface_variant"],
            font=("Inter", 11),
            anchor="w",
        ).grid(row=0, column=1, padx=(0, 8), pady=8, sticky="w")

        ctk.CTkLabel(right, text="ANALYSIS MODE", text_color=TOKENS["on_surface_variant"], font=("Inter", 10, "bold")).grid(
            row=4, column=0, padx=12, pady=(0, 6), sticky="w"
        )
        self.scope_menu = ctk.CTkOptionMenu(
            right,
            values=["auto", "direct", "profile_collection"],
            variable=self.scope_var,
            fg_color=TOKENS["surface_container_lowest"],
            button_color=TOKENS["surface_container_highest"],
            dropdown_fg_color=TOKENS["surface_container_low"],
            corner_radius=8,
        )
        self.scope_menu.grid(row=5, column=0, padx=12, pady=(4, 10), sticky="ew")

        ctk.CTkLabel(right, text="Collection limit", text_color=TOKENS["on_surface"], font=("Inter", 12)).grid(
            row=6, column=0, padx=12, sticky="w"
        )
        self.max_items_entry = ctk.CTkEntry(
            right,
            textvariable=self.max_items_var,
            fg_color=TOKENS["surface_container_lowest"],
            border_width=0,
            corner_radius=8,
            width=120,
        )
        self.max_items_entry.grid(row=7, column=0, padx=12, pady=(4, 10), sticky="w")

        self.video_only_switch = ctk.CTkSwitch(
            right,
            text="Videos only",
            variable=self.video_only_var,
            progress_color=TOKENS["primary_container"],
            button_color="white",
            font=("Inter", 11),
        )
        self.video_only_switch.grid(row=8, column=0, padx=12, pady=(0, 12), sticky="w")

        storage = ctk.CTkFrame(self, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        storage.grid(row=3, column=0, pady=(14, 0), sticky="ew")
        storage.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(storage, text="STORAGE & FILE SYSTEM", text_color=TOKENS["on_surface_variant"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        out_row = ctk.CTkFrame(storage, fg_color="transparent")
        out_row.grid(row=1, column=0, padx=12, sticky="ew")
        out_row.grid_columnconfigure(0, weight=1)

        self.output_entry = ctk.CTkEntry(
            out_row,
            textvariable=self.output_dir_var,
            fg_color=TOKENS["surface_container_lowest"],
            border_width=0,
            corner_radius=8,
            text_color=TOKENS["on_surface"],
            font=("Consolas", 11),
            height=38,
        )
        self.output_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            out_row,
            text="BROWSE",
            fg_color=TOKENS["surface_container_high"],
            hover_color=TOKENS["surface_bright"],
            corner_radius=8,
            width=100,
            command=self._on_browse,
        ).grid(row=0, column=1, sticky="e")

        toggles = ctk.CTkFrame(storage, fg_color="transparent")
        toggles.grid(row=2, column=0, padx=12, pady=(12, 12), sticky="ew")
        toggles.grid_columnconfigure((0, 1, 2), weight=1)

        self.auto_switch = ctk.CTkSwitch(
            toggles,
            text="Playlist Subfolders",
            variable=self.auto_subfolder_var,
            progress_color=TOKENS["primary_container"],
            button_color="white",
            font=("Inter", 11),
        )
        self.auto_switch.grid(row=0, column=0, sticky="w")

        self.sound_switch = ctk.CTkSwitch(
            toggles,
            text="Completion Sound",
            variable=self.sound_var,
            progress_color=TOKENS["primary_container"],
            button_color="white",
            font=("Inter", 11),
        )
        self.sound_switch.grid(row=0, column=1, sticky="w")

        self.dark_switch = ctk.CTkSwitch(
            toggles,
            text="Dark Mode",
            variable=self.dark_mode_var,
            progress_color=TOKENS["primary_container"],
            button_color="white",
            font=("Inter", 11),
        )
        self.dark_switch.grid(row=0, column=2, sticky="w")

        auth = ctk.CTkFrame(self, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        auth.grid(row=4, column=0, pady=(14, 0), sticky="ew")
        auth.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(auth, text="AUTHENTICATION", text_color=TOKENS["on_surface_variant"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, padx=12, pady=(12, 6), sticky="w"
        )

        ctk.CTkLabel(auth, text="Cookies mode", text_color=TOKENS["on_surface"], font=("Inter", 12)).grid(
            row=1, column=0, padx=12, sticky="w"
        )
        self.cookies_mode_menu = ctk.CTkOptionMenu(
            auth,
            values=["auto", "browser", "file", "off"],
            variable=self.cookies_mode_var,
            fg_color=TOKENS["surface_container_lowest"],
            button_color=TOKENS["surface_container_highest"],
            dropdown_fg_color=TOKENS["surface_container_low"],
            corner_radius=8,
        )
        self.cookies_mode_menu.grid(row=2, column=0, padx=12, pady=(4, 10), sticky="ew")

        ctk.CTkLabel(auth, text="Browser source", text_color=TOKENS["on_surface"], font=("Inter", 12)).grid(
            row=3, column=0, padx=12, sticky="w"
        )
        self.cookies_browser_menu = ctk.CTkOptionMenu(
            auth,
            values=["chrome", "edge", "firefox", "brave"],
            variable=self.cookies_browser_var,
            fg_color=TOKENS["surface_container_lowest"],
            button_color=TOKENS["surface_container_highest"],
            dropdown_fg_color=TOKENS["surface_container_low"],
            corner_radius=8,
        )
        self.cookies_browser_menu.grid(row=4, column=0, padx=12, pady=(4, 10), sticky="ew")

        cookie_row = ctk.CTkFrame(auth, fg_color="transparent")
        cookie_row.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")
        cookie_row.grid_columnconfigure(0, weight=1)

        self.cookies_file_entry = ctk.CTkEntry(
            cookie_row,
            textvariable=self.cookies_file_var,
            fg_color=TOKENS["surface_container_lowest"],
            border_width=0,
            corner_radius=8,
            text_color=TOKENS["on_surface"],
            font=("Consolas", 11),
            height=38,
            placeholder_text="cookies.txt path",
        )
        self.cookies_file_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            cookie_row,
            text="BROWSE",
            fg_color=TOKENS["surface_container_high"],
            hover_color=TOKENS["surface_bright"],
            corner_radius=8,
            width=100,
            command=self._on_browse_cookies,
        ).grid(row=0, column=1, sticky="e")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=5, column=0, pady=(12, 0), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer,
            text="Restore Defaults",
            fg_color="transparent",
            hover_color=TOKENS["surface_container_high"],
            text_color=TOKENS["on_surface_variant"],
            corner_radius=8,
            command=self._restore_defaults,
            width=140,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            footer,
            text="Apply Changes",
            fg_color=TOKENS["red"],
            hover_color=TOKENS["primary_container"],
            text_color="white",
            corner_radius=8,
            command=self._apply,
            width=140,
        ).grid(row=0, column=1, sticky="e")

    def _restore_defaults(self) -> None:
        self.quality_var.set("1080p")
        self.format_var.set("MP4")
        self.parallel_var.set("2")
        self.auto_subfolder_var.set(True)
        self.sound_var.set(True)
        self.dark_mode_var.set(True)
        self.scope_var.set("auto")
        self.max_items_var.set("50")
        self.video_only_var.set(True)
        self.cookies_mode_var.set("auto")
        self.cookies_browser_var.set("chrome")
        self.cookies_file_var.set("")

    def _apply(self) -> None:
        try:
            parallel = int(self.parallel_var.get().strip())
        except ValueError:
            parallel = 2
        parallel = max(1, min(3, parallel))

        try:
            max_items = int(self.max_items_var.get().strip())
        except ValueError:
            max_items = 50
        max_items = max(1, min(500, max_items))

        values = {
            "quality": self.quality_var.get(),
            "format": self.format_var.get(),
            "parallel": parallel,
            "output_dir": self.output_dir_var.get().strip() or str(Path.home()),
            "auto_subfolder": bool(self.auto_subfolder_var.get()),
            "sound": bool(self.sound_var.get()),
            "dark_mode": bool(self.dark_mode_var.get()),
            "scope_mode": self.scope_var.get().strip() or "auto",
            "max_items": max_items,
            "video_only": bool(self.video_only_var.get()),
            "cookies_mode": self.cookies_mode_var.get().strip() or "auto",
            "cookies_browser": self.cookies_browser_var.get().strip() or "chrome",
            "cookies_file": self.cookies_file_var.get().strip(),
        }
        self._on_apply(values)

    def set_output_dir(self, path: str) -> None:
        self.output_dir_var.set(path)

    def set_dark_mode(self, is_dark: bool) -> None:
        self.dark_mode_var.set(is_dark)

    def set_cookies_file(self, path: str) -> None:
        self.cookies_file_var.set(path)
