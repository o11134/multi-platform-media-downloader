from __future__ import annotations

import os
import queue
import shutil
import socket
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from core.analyzer import AnalysisOptions, InvalidUrlError, PlaylistAnalyzer, PlaylistInfo, PlaylistUnavailableError, format_duration
from core.database import HistoryDatabase, HistoryEntry
from core.downloader import DownloadManager, DownloadOptions, DownloadTask
from core.preferences import AppPreferences, PreferencesStore
from ui.playlist_view import PlaylistView
from ui.settings import SettingsView

try:
    from win10toast import ToastNotifier
except Exception:  # noqa: BLE001
    ToastNotifier = None

try:
    import winsound
except Exception:  # noqa: BLE001
    winsound = None


TOKENS = {
    "surface": "#131313",
    "surface_container_low": "#1b1b1c",
    "surface_container": "#202020",
    "surface_container_high": "#2a2a2a",
    "surface_container_highest": "#353535",
    "surface_bright": "#393939",
    "surface_container_lowest": "#0e0e0e",
    "on_surface": "#e5e2e1",
    "on_surface_variant": "#ebbbb4",
    "muted": "#474747",
    "primary": "#ffb4a8",
    "primary_container": "#ff5540",
    "red": "#FF0000",
}


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Kinetic Downloader")
        self.geometry("1400x860")
        self.minsize(1200, 750)
        self.configure(fg_color=TOKENS["surface"])

        self._app_data_dir = self._get_app_data_dir()
        self._thumbnail_cache_dir = self._app_data_dir / "thumb_cache"
        self._history_db_path = self._app_data_dir / "history.db"
        self._preferences_path = self._app_data_dir / "preferences.json"
        self._preferences_store = PreferencesStore(self._preferences_path)
        self._preferences = self._preferences_store.load()

        self._set_appearance(self._preferences.appearance_mode)

        self._analyzer = PlaylistAnalyzer()
        self._database = HistoryDatabase(self._history_db_path, max_records=500)
        self._download_events: queue.Queue[dict] = queue.Queue()
        self._download_manager = DownloadManager(self._on_download_event)
        self._analysis_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analyze")

        self._analysis_lock = threading.Lock()
        self._analysis_in_flight = False
        self._playlist_info: PlaylistInfo | None = None
        self._video_pause_state: dict[str, bool] = {}

        self._notification_enabled = self._preferences.notifications_enabled
        self._sound_enabled = self._preferences.sound_enabled
        self._toaster = ToastNotifier() if ToastNotifier else None

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._pages: dict[str, Any] = {}

        default_out = Path.home() / "Downloads"
        if not default_out.exists():
            default_out = Path.home()
        pref_folder = Path(self._preferences.last_output_dir) if self._preferences.last_output_dir else default_out
        if not pref_folder.exists():
            pref_folder = default_out

        self.url_var = ctk.StringVar()
        quality_default = self._preferences.quality if self._preferences.quality in {"1080p", "720p", "480p", "360p", "Audio Only"} else "1080p"
        format_default = self._preferences.file_format if self._preferences.file_format in {"MP4", "MKV", "MP3", "M4A"} else "MP4"
        self.quality_var = ctk.StringVar(value=quality_default)
        self.format_var = ctk.StringVar(value=format_default)
        self.output_dir_var = ctk.StringVar(value=str(pref_folder))
        self.auto_subfolder_var = ctk.BooleanVar(value=self._preferences.auto_subfolder)
        self.parallel_var = ctk.IntVar(value=max(1, min(3, int(self._preferences.parallel_downloads))))
        self.scope_mode_var = ctk.StringVar(value=self._preferences.scope_mode)
        self.max_items_var = ctk.IntVar(value=max(1, min(500, int(self._preferences.max_items))))
        self.video_only_var = ctk.BooleanVar(value=self._preferences.video_only)
        self.cookies_mode_var = ctk.StringVar(value=self._preferences.cookies_mode)
        self.cookies_browser_var = ctk.StringVar(value=self._preferences.cookies_browser)
        self.cookies_file_var = ctk.StringVar(value=self._preferences.cookies_file)

        self._build_shell()
        self._build_dashboard_page()
        self._build_playlist_page()
        self._build_history_page()
        self._build_settings_page()
        self._switch_page("dashboard")
        self._refresh_history_table()
        self.settings_view.set_output_dir(self.output_dir_var.get())
        self.settings_view.set_cookies_file(self.cookies_file_var.get())
        self.settings_view.set_dark_mode(ctk.get_appearance_mode().lower() != "light")
        self._refresh_status_bar()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_download_events)

    def _build_shell(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=240)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=0, minsize=56)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0, minsize=32)

        self.sidebar = ctk.CTkFrame(self, fg_color=TOKENS["surface_container_low"], corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(6, weight=1)

        logo = ctk.CTkLabel(
            self.sidebar,
            text="Kinetic Downloader",
            text_color=TOKENS["red"],
            font=("Inter", 22, "bold"),
            anchor="w",
        )
        logo.grid(row=0, column=0, padx=16, pady=(18, 4), sticky="ew")

        meta = ctk.CTkLabel(
            self.sidebar,
            text="PRO CONSOLE   v2.4.0",
            text_color=TOKENS["muted"],
            font=("Inter", 10, "bold"),
            anchor="w",
        )
        meta.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="ew")

        nav_items = [
            ("dashboard", "⊞  Dashboard"),
            ("playlists", "▶☰  Playlists"),
            ("history", "↺  History"),
            ("settings", "⚙  Settings"),
        ]
        for idx, (key, text) in enumerate(nav_items, start=2):
            btn = ctk.CTkButton(
                self.sidebar,
                text=text,
                fg_color=TOKENS["surface_container_low"],
                hover_color=TOKENS["surface_container_high"],
                text_color=TOKENS["on_surface_variant"],
                corner_radius=8,
                height=44,
                anchor="w",
                command=lambda k=key: self._switch_page(k),
            )
            btn.grid(row=idx, column=0, padx=12, pady=4, sticky="ew")
            self._nav_buttons[key] = btn

        user_card = ctk.CTkFrame(self.sidebar, fg_color=TOKENS["surface_container_high"], corner_radius=10)
        user_card.grid(row=7, column=0, padx=12, pady=12, sticky="ew")
        user_card.grid_columnconfigure(1, weight=1)

        avatar = ctk.CTkLabel(user_card, text="👤", width=40, height=40, fg_color=TOKENS["surface_bright"], corner_radius=20)
        avatar.grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkLabel(user_card, text="Admin Console", text_color=TOKENS["on_surface"], font=("Inter", 12, "bold")).grid(
            row=0, column=1, padx=(0, 6), pady=(8, 2), sticky="w"
        )
        ctk.CTkLabel(user_card, text="SYSTEM ACTIVE", text_color=TOKENS["on_surface_variant"], font=("Inter", 10)).grid(
            row=1, column=1, padx=(0, 6), pady=(0, 8), sticky="w"
        )

        self.topbar = ctk.CTkFrame(self, fg_color=TOKENS["surface_container_low"], corner_radius=0, height=56)
        self.topbar.grid(row=0, column=1, sticky="ew")
        self.topbar.grid_columnconfigure(0, weight=1)
        self.topbar.grid_propagate(False)

        self.breadcrumb_label = ctk.CTkLabel(
            self.topbar,
            text="⚡ SYSTEM OPERATIONS / DASHBOARD",
            text_color=TOKENS["muted"],
            font=("Inter", 11, "bold"),
            anchor="w",
        )
        self.breadcrumb_label.grid(row=0, column=0, padx=20, pady=16, sticky="w")

        top_actions = ctk.CTkFrame(self.topbar, fg_color="transparent")
        top_actions.grid(row=0, column=1, padx=16, pady=10, sticky="e")
        top_actions.grid_columnconfigure((0, 1, 2), weight=0)

        self.theme_btn = ctk.CTkButton(
            top_actions,
            text="◐",
            width=34,
            height=34,
            corner_radius=17,
            fg_color=TOKENS["surface_container_low"],
            hover_color=TOKENS["surface_container_high"],
            command=self._toggle_theme,
        )
        self.theme_btn.grid(row=0, column=0, padx=(0, 8))

        self.settings_icon_btn = ctk.CTkButton(
            top_actions,
            text="⚙",
            width=34,
            height=34,
            corner_radius=17,
            fg_color=TOKENS["surface_container_low"],
            hover_color=TOKENS["surface_container_high"],
            command=lambda: self._switch_page("settings"),
        )
        self.settings_icon_btn.grid(row=0, column=1, padx=(0, 8))

        self.account_icon_btn = ctk.CTkButton(
            top_actions,
            text="👤",
            width=34,
            height=34,
            corner_radius=17,
            fg_color=TOKENS["surface_container_low"],
            hover_color=TOKENS["surface_container_high"],
            command=lambda: None,
        )
        self.account_icon_btn.grid(row=0, column=2)

        self.main_host = ctk.CTkFrame(self, fg_color=TOKENS["surface"], corner_radius=0)
        self.main_host.grid(row=1, column=1, sticky="nsew")
        self.main_host.grid_columnconfigure(0, weight=1)
        self.main_host.grid_rowconfigure(0, weight=1)

        self.statusbar = ctk.CTkFrame(self, fg_color=TOKENS["surface_container_low"], corner_radius=0, height=32)
        self.statusbar.grid(row=2, column=1, sticky="ew")
        self.statusbar.grid_columnconfigure(0, weight=1)
        self.statusbar.grid_propagate(False)

        status_wrap = ctk.CTkFrame(self.statusbar, fg_color="transparent")
        status_wrap.grid(row=0, column=1, padx=16, pady=6, sticky="e")
        self.network_status_label = ctk.CTkLabel(
            status_wrap,
            text="NETWORK: CONNECTED",
            text_color=TOKENS["muted"],
            font=("Inter", 10, "bold"),
        )
        self.network_status_label.grid(row=0, column=0, padx=8)

        self.storage_status_label = ctk.CTkLabel(
            status_wrap,
            text="STORAGE: -- GB FREE",
            text_color=TOKENS["muted"],
            font=("Inter", 10, "bold"),
        )
        self.storage_status_label.grid(row=0, column=1, padx=8)

        self.ready_status_label = ctk.CTkLabel(
            status_wrap,
            text="● STATUS: READY",
            text_color=TOKENS["red"],
            font=("Inter", 10, "bold"),
        )
        self.ready_status_label.grid(row=0, column=2, padx=8)

    def _make_page(self) -> ctk.CTkScrollableFrame:
        page = ctk.CTkScrollableFrame(
            self.main_host,
            fg_color=TOKENS["surface"],
            corner_radius=0,
            scrollbar_button_color=TOKENS["surface_container_highest"],
            scrollbar_button_hover_color=TOKENS["surface_bright"],
        )
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        return page

    def _build_dashboard_page(self) -> None:
        page = self._make_page()
        self._pages["dashboard"] = page

        content = ctk.CTkFrame(page, fg_color="transparent")
        content.grid(row=0, column=0, padx=32, pady=24, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        hero = ctk.CTkFrame(content, fg_color="transparent")
        hero.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        hero.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            hero,
            text="INPUT STREAM",
            text_color=TOKENS["on_surface"],
            font=("Inter", 36, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            hero,
            text="Paste a YouTube / Instagram / TikTok / X URL to begin extraction.",
            text_color=TOKENS["muted"],
            font=("Inter", 12),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        row = ctk.CTkFrame(hero, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew")
        row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            row,
            textvariable=self.url_var,
            fg_color="#0e0e0e",
            border_width=1,
            border_color="#603e39",
            corner_radius=8,
            text_color=TOKENS["on_surface"],
            placeholder_text="https://www.instagram.com/... or https://x.com/...",
            font=("Consolas", 12),
            height=48,
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.paste_btn = ctk.CTkButton(
            row,
            text="PASTE",
            fg_color=TOKENS["surface_container_high"],
            hover_color=TOKENS["surface_bright"],
            corner_radius=8,
            command=self._paste_url,
            width=90,
            height=48,
            font=("Inter", 11, "bold"),
        )
        self.paste_btn.grid(row=0, column=1, padx=(0, 10))

        self.analyze_btn = ctk.CTkButton(
            row,
            text="ANALYZE",
            fg_color=TOKENS["red"],
            hover_color=TOKENS["primary_container"],
            corner_radius=8,
            command=self._analyze_playlist,
            width=110,
            height=48,
            font=("Inter", 11, "bold"),
        )
        self.analyze_btn.grid(row=0, column=2)

        mode_row = ctk.CTkFrame(hero, fg_color="transparent")
        mode_row.grid(row=3, column=0, sticky="w", pady=(8, 0))

        ctk.CTkLabel(
            mode_row,
            text="MODE",
            text_color=TOKENS["muted"],
            font=("Inter", 10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=(0, 8), sticky="w")

        ctk.CTkOptionMenu(
            mode_row,
            values=["auto", "direct", "profile_collection"],
            variable=self.scope_mode_var,
            fg_color=TOKENS["surface_container_lowest"],
            button_color=TOKENS["surface_container_highest"],
            dropdown_fg_color=TOKENS["surface_container_low"],
            corner_radius=8,
            width=180,
        ).grid(row=0, column=1, sticky="w")

        analyzer_card = ctk.CTkFrame(content, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        analyzer_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 14))
        analyzer_card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(analyzer_card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 6))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="MODULE: EXTRACTOR V2",
            fg_color=TOKENS["surface_container_high"],
            text_color=TOKENS["muted"],
            corner_radius=6,
            padx=8,
            pady=3,
            font=("Inter", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.analyzer_status = ctk.CTkLabel(
            top,
            text="● STATUS: IDLE",
            fg_color=TOKENS["surface_container_lowest"],
            text_color=TOKENS["muted"],
            corner_radius=12,
            padx=10,
            pady=4,
            font=("Inter", 10, "bold"),
        )
        self.analyzer_status.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(analyzer_card, text="Media Analyzer", text_color=TOKENS["on_surface"], font=("Inter", 24, "bold")).grid(
            row=1, column=0, sticky="w", padx=14, pady=(0, 10)
        )

        stats = ctk.CTkFrame(analyzer_card, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        stats.grid_columnconfigure((0, 1), weight=1)

        left_stat = ctk.CTkFrame(stats, fg_color=TOKENS["surface_container_high"], corner_radius=10)
        left_stat.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkLabel(left_stat, text="ITEMS FOUND", text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0)
        )
        self.items_found_value = ctk.CTkLabel(left_stat, text="0 VIDEOS", text_color=TOKENS["on_surface"], font=("Inter", 24, "bold"))
        self.items_found_value.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        right_stat = ctk.CTkFrame(stats, fg_color=TOKENS["surface_container_high"], corner_radius=10)
        right_stat.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ctk.CTkLabel(right_stat, text="AGGREGATED LENGTH", text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 0)
        )
        self.duration_value = ctk.CTkLabel(right_stat, text="0:00 DURATION", text_color=TOKENS["on_surface"], font=("Inter", 24, "bold"))
        self.duration_value.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 10))

        storage_card = ctk.CTkFrame(content, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        storage_card.grid(row=1, column=1, sticky="nsew", padx=(10, 0), pady=(0, 14))
        storage_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(storage_card, text="STORAGE METRICS", text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=14, pady=(14, 6)
        )
        self.storage_text = ctk.CTkLabel(
            storage_card,
            text="Local Cache  1.2 GB / 50 GB",
            text_color=TOKENS["on_surface"],
            font=("Inter", 12),
            anchor="w",
        )
        self.storage_text.grid(row=1, column=0, sticky="ew", padx=14)

        self.storage_bar = ctk.CTkProgressBar(
            storage_card,
            fg_color=TOKENS["surface_container_highest"],
            progress_color=TOKENS["primary"],
            height=6,
            corner_radius=3,
        )
        self.storage_bar.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 16))
        self.storage_bar.set(0.024)

        ctk.CTkLabel(storage_card, text="FORMAT PRIORITY", text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
            row=3, column=0, sticky="w", padx=14, pady=(0, 6)
        )
        self.video_output_label = ctk.CTkLabel(
            storage_card,
            text="Video Output ............. MP4 4K",
            text_color=TOKENS["red"],
            font=("Consolas", 11),
            anchor="w",
        )
        self.video_output_label.grid(row=4, column=0, sticky="ew", padx=14)

        self.audio_output_label = ctk.CTkLabel(
            storage_card,
            text="Audio Output ............. OPUS 160K",
            text_color=TOKENS["red"],
            font=("Consolas", 11),
            anchor="w",
        )
        self.audio_output_label.grid(row=5, column=0, sticky="ew", padx=14, pady=(4, 14))

        transfer = ctk.CTkFrame(content, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        transfer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        transfer.grid_columnconfigure(0, weight=1)

        top_line = ctk.CTkFrame(transfer, fg_color="transparent")
        top_line.grid(row=0, column=0, sticky="ew", padx=14, pady=(14, 8))
        top_line.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top_line,
            text="⭳ TRANSFER MANAGEMENT",
            text_color=TOKENS["on_surface"],
            font=("Inter", 18, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.transfer_status = ctk.CTkLabel(
            transfer,
            text="Status: Ready to download",
            text_color=TOKENS["red"],
            font=("Inter", 12, "bold"),
            anchor="w",
        )
        self.transfer_status.grid(row=1, column=0, padx=14, pady=(0, 2), sticky="w")

        self.init_download_btn = ctk.CTkButton(
            transfer,
            text="Initialize Sequential Download",
            fg_color=TOKENS["surface_container_high"],
            hover_color=TOKENS["surface_bright"],
            state="disabled",
            corner_radius=8,
            width=250,
            command=self._start_download,
        )
        self.init_download_btn.grid(row=2, column=0, padx=14, pady=(8, 8), sticky="w")

        self.global_progress_label = ctk.CTkLabel(
            transfer,
            text="GLOBAL PROGRESS  0%",
            text_color=TOKENS["on_surface_variant"],
            font=("Inter", 10, "bold"),
            anchor="e",
        )
        self.global_progress_label.grid(row=3, column=0, padx=14, sticky="e")

        self.overall_progress = ctk.CTkProgressBar(
            transfer,
            fg_color=TOKENS["surface_container_highest"],
            progress_color=TOKENS["primary"],
            height=12,
            corner_radius=6,
        )
        self.overall_progress.grid(row=4, column=0, padx=14, pady=(10, 8), sticky="ew")
        self.overall_progress.set(0.0)

        self.queue_status = ctk.CTkLabel(
            transfer,
            text="AWAITING TASK QUEUE...   0 KB/S",
            text_color=TOKENS["muted"],
            font=("Consolas", 11),
            anchor="w",
        )
        self.queue_status.grid(row=5, column=0, padx=14, pady=(0, 14), sticky="ew")

    def _build_playlist_page(self) -> None:
        page = self._make_page()
        self._pages["playlists"] = page

        host = ctk.CTkFrame(page, fg_color="transparent")
        host.grid(row=0, column=0, padx=24, pady=24, sticky="nsew")
        host.grid_columnconfigure(0, weight=1)
        host.grid_rowconfigure(0, weight=1)

        self.playlist_view = PlaylistView(
            host,
            cache_dir=self._thumbnail_cache_dir,
            on_pause_resume=self._toggle_video_pause_resume,
            on_copy_link=self._copy_video_link,
        )
        self.playlist_view.grid(row=0, column=0, sticky="nsew")
        self.playlist_view.set_start_download_command(self._start_download)

    def _build_history_page(self) -> None:
        page = self._make_page()
        self._pages["history"] = page

        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.grid(row=0, column=0, padx=32, pady=24, sticky="nsew")
        wrap.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(wrap, text="TELEMETRY LOGS", text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ctk.CTkLabel(wrap, text="Download History", text_color=TOKENS["on_surface"], font=("Inter", 34, "bold")).grid(
            row=1, column=0, columnspan=2, sticky="w"
        )

        actions = ctk.CTkFrame(wrap, fg_color="transparent")
        actions.grid(row=1, column=2, columnspan=2, sticky="e")
        self.clear_history_btn = ctk.CTkButton(
            actions,
            text="CLEAR HISTORY",
            fg_color=TOKENS["surface_container_high"],
            hover_color=TOKENS["surface_bright"],
            corner_radius=8,
            command=self._clear_history,
        )
        self.clear_history_btn.grid(row=0, column=0, padx=(0, 8))
        self.retry_failed_btn = ctk.CTkButton(
            actions,
            text="↻ RETRY FAILED",
            fg_color=TOKENS["red"],
            hover_color=TOKENS["primary_container"],
            corner_radius=8,
            command=lambda: messagebox.showinfo("Retry Failed", "Retry queue trigger placeholder."),
        )
        self.retry_failed_btn.grid(row=0, column=1)

        self.history_stats: list[ctk.CTkLabel] = []
        stat_titles = ["TOTAL RECORDS", "SUCCESSFUL", "FAILED", "DATA SAVED"]
        for i, title in enumerate(stat_titles):
            card = ctk.CTkFrame(wrap, fg_color=TOKENS["surface_container_low"], corner_radius=12)
            card.grid(row=2, column=i, padx=6, pady=(14, 12), sticky="ew")
            ctk.CTkLabel(card, text=title, text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
                row=0, column=0, padx=12, pady=(10, 0), sticky="w"
            )
            value = ctk.CTkLabel(card, text="0", text_color=TOKENS["on_surface"], font=("Inter", 28, "bold"))
            value.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
            self.history_stats.append(value)

        table = ctk.CTkFrame(wrap, fg_color=TOKENS["surface_container_low"], corner_radius=12)
        table.grid(row=3, column=0, columnspan=4, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(1, weight=1)
        wrap.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(table, fg_color=TOKENS["surface_container_high"], corner_radius=8)
        header.grid(row=0, column=0, padx=12, pady=12, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        for idx, col in enumerate(["DATE & TIME", "MEDIA TITLE", "STATUS", "ERROR CODE", "ACTIONS"]):
            ctk.CTkLabel(header, text=col, text_color=TOKENS["muted"], font=("Inter", 10, "bold")).grid(
                row=0, column=idx, padx=8, pady=8, sticky="w"
            )

        self.history_list = ctk.CTkScrollableFrame(
            table,
            fg_color=TOKENS["surface_container_low"],
            corner_radius=0,
            scrollbar_button_color=TOKENS["surface_container_highest"],
            scrollbar_button_hover_color=TOKENS["surface_bright"],
        )
        self.history_list.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="nsew")
        self.history_list.grid_columnconfigure(1, weight=1)

        footer = ctk.CTkFrame(table, fg_color="transparent")
        footer.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        footer.grid_columnconfigure(0, weight=1)
        self.history_page_label = ctk.CTkLabel(
            footer,
            text="Showing 1-5 of 0 records",
            text_color=TOKENS["muted"],
            font=("Inter", 11),
            anchor="w",
        )
        self.history_page_label.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(footer, text="Previous", fg_color=TOKENS["surface_container_high"], width=90).grid(row=0, column=1, padx=(0, 6))
        ctk.CTkButton(footer, text="Next", fg_color=TOKENS["surface_container_high"], width=90).grid(row=0, column=2)

    def _build_settings_page(self) -> None:
        page = self._make_page()
        self._pages["settings"] = page

        self.settings_view = SettingsView(
            page,
            preferences=self._preferences,
            on_browse=self._pick_output_folder,
            on_browse_cookies=self._pick_cookies_file,
            on_apply=self._apply_settings_values,
        )
        self.settings_view.grid(row=0, column=0, padx=32, pady=24, sticky="nsew")

    def _switch_page(self, page_key: str) -> None:
        for key, page in self._pages.items():
            if key == page_key:
                page.grid()
            else:
                page.grid_remove()

        for key, btn in self._nav_buttons.items():
            if key == page_key:
                btn.configure(fg_color=TOKENS["red"], hover_color=TOKENS["primary_container"], text_color="white")
            else:
                btn.configure(
                    fg_color=TOKENS["surface_container_low"],
                    hover_color=TOKENS["surface_container_high"],
                    text_color=TOKENS["on_surface_variant"],
                )

        self.breadcrumb_label.configure(text=f"⚡ SYSTEM OPERATIONS / {page_key.upper()}")
        if page_key == "history":
            self._refresh_history_table()

    def _paste_url(self) -> None:
        try:
            self.url_var.set(self.clipboard_get())
        except Exception:
            pass

    def _analyze_playlist(self) -> None:
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please paste a media URL first.")
            return

        with self._analysis_lock:
            if self._analysis_in_flight:
                return
            self._analysis_in_flight = True

        self.analyze_btn.configure(state="disabled", text="ANALYZING...")
        self.analyzer_status.configure(text="● STATUS: RUNNING", text_color=TOKENS["primary"])

        try:
            max_items = int(self.max_items_var.get())
        except Exception:
            max_items = 50

        analysis_options = AnalysisOptions(
            scope_mode=self.scope_mode_var.get().strip() or "auto",
            max_items=max(1, min(500, max_items)),
            video_only=bool(self.video_only_var.get()),
            cookies_mode=self.cookies_mode_var.get().strip() or "auto",
            cookies_browser=self.cookies_browser_var.get().strip() or "chrome",
            cookies_file=self.cookies_file_var.get().strip(),
        )

        future: Future[PlaylistInfo] = self._analysis_executor.submit(self._analyzer.analyze, url, analysis_options)
        future.add_done_callback(lambda f: self.after(0, self._on_analysis_complete, f))

    def _on_analysis_complete(self, future: Future[PlaylistInfo]) -> None:
        with self._analysis_lock:
            self._analysis_in_flight = False

        self.analyze_btn.configure(state="normal", text="ANALYZE")

        try:
            playlist = future.result()
        except InvalidUrlError as exc:
            self.analyzer_status.configure(text="● STATUS: ERROR", text_color=TOKENS["red"])
            messagebox.showerror("Invalid URL", str(exc))
            return
        except PlaylistUnavailableError as exc:
            self.analyzer_status.configure(text="● STATUS: ERROR", text_color=TOKENS["red"])
            messagebox.showerror("Media Error", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            self.analyzer_status.configure(text="● STATUS: ERROR", text_color=TOKENS["red"])
            messagebox.showerror("Analyze Failed", f"Unexpected error: {exc}")
            return

        self._playlist_info = playlist
        self._video_pause_state = {v.video_id: False for v in playlist.videos}
        self.items_found_value.configure(text=f"{playlist.video_count} VIDEOS")
        self.duration_value.configure(text=f"{format_duration(playlist.total_duration_seconds)} DURATION")
        platform_label = {
            "youtube": "YOUTUBE",
            "instagram": "INSTAGRAM",
            "tiktok": "TIKTOK",
            "x": "X",
        }.get(playlist.source_platform, "UNKNOWN")
        self.analyzer_status.configure(text=f"● STATUS: {platform_label}", text_color=TOKENS["muted"])
        self.transfer_status.configure(text="Status: Ready to download")
        self.init_download_btn.configure(state="normal")

        self.playlist_view.set_videos(playlist.videos)
        self.playlist_view.set_playlist_header(
            playlist.title,
            playlist.video_count,
            playlist.total_duration_seconds,
            source_platform=playlist.source_platform,
            source_kind=playlist.source_kind,
        )
        self.playlist_view.reset_progress()

        self._switch_page("playlists")

    def _start_download(self) -> None:
        if self._download_manager.is_running:
            return
        if not self._playlist_info:
            messagebox.showwarning("Analyze First", "Analyze a media URL before downloading.")
            return

        selected_ids = self.playlist_view.selected_video_ids()
        if not selected_ids:
            messagebox.showwarning("No Selection", "Select at least one video.")
            return

        output_dir = Path(self.output_dir_var.get().strip())
        output_dir.mkdir(parents=True, exist_ok=True)
        if self.auto_subfolder_var.get():
            output_dir = output_dir / self._sanitize_folder_name(self._playlist_info.title)
            output_dir.mkdir(parents=True, exist_ok=True)

        tasks: list[DownloadTask] = []
        for video_id in selected_ids:
            video = self.playlist_view.get_video(video_id)
            if video:
                tasks.append(DownloadTask(video_id=video.video_id, title=video.title, url=video.webpage_url, duration_seconds=video.duration_seconds))

        options = DownloadOptions(
            quality=self.quality_var.get(),
            file_format=self.format_var.get(),
            output_dir=output_dir,
            parallel_downloads=max(1, min(3, int(self.parallel_var.get()))),
            max_retries=3,
            cookies_mode=self.cookies_mode_var.get().strip() or "auto",
            cookies_browser=self.cookies_browser_var.get().strip() or "chrome",
            cookies_file=self.cookies_file_var.get().strip(),
        )

        self.transfer_status.configure(text="Status: Downloading...", text_color=TOKENS["primary"])
        self.init_download_btn.configure(state="disabled")
        self.playlist_view.reset_progress()
        self.queue_status.configure(text="INITIALIZING DOWNLOAD QUEUE...  0 KB/S")

        try:
            self._download_manager.start_batch(self._playlist_info.title, tasks, options)
        except Exception as exc:  # noqa: BLE001
            self.transfer_status.configure(text="Status: Ready to download", text_color=TOKENS["red"])
            self.init_download_btn.configure(state="normal")
            messagebox.showerror("Download Error", str(exc))

    def _toggle_video_pause_resume(self, video_id: str) -> None:
        if not self._download_manager.is_running:
            return
        paused = self._video_pause_state.get(video_id, False)
        if paused:
            self._download_manager.resume_task(video_id)
            self._video_pause_state[video_id] = False
        else:
            self._download_manager.pause_task(video_id)
            self._video_pause_state[video_id] = True

    def _copy_video_link(self, video_id: str) -> None:
        video = self.playlist_view.get_video(video_id)
        if not video:
            return
        self.clipboard_clear()
        self.clipboard_append(video.webpage_url)

    def _on_download_event(self, event: dict) -> None:
        self._download_events.put(event)

    def _drain_download_events(self) -> None:
        while True:
            try:
                event = self._download_events.get_nowait()
            except queue.Empty:
                break
            self._handle_download_event(event)
        self.after(100, self._drain_download_events)

    def _handle_download_event(self, event: dict) -> None:
        event_type = event.get("type")

        if event_type == "task_progress":
            video_id = str(event.get("video_id", ""))
            percent = float(event.get("percent", 0.0))
            speed = float(event.get("speed", 0.0))
            self.playlist_view.update_progress(video_id, percent)
            self.playlist_view.mark_status(video_id, "DOWNLOADING", color=TOKENS["primary"])
            self.queue_status.configure(text=f"ACTIVE TRANSFER...  {self._format_bytes(speed)}/S")
            self.ready_status_label.configure(text="● STATUS: ACTIVE")
            return

        if event_type == "task_processing":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.mark_status(video_id, "DOWNLOADING", color=TOKENS["primary"])
            return

        if event_type == "task_queued":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.mark_status(video_id, "QUEUED", color=TOKENS["on_surface_variant"])
            return

        if event_type == "task_started":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.mark_status(video_id, "DOWNLOADING", color=TOKENS["primary"])
            return

        if event_type == "task_retrying":
            video_id = str(event.get("video_id", ""))
            delay = int(float(event.get("delay_seconds", 0)))
            self.playlist_view.mark_status(video_id, f"RETRY IN {delay}s", color=TOKENS["on_surface_variant"])
            return

        if event_type == "task_paused":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.set_paused(video_id, True)
            self.playlist_view.mark_status(video_id, "QUEUED", color=TOKENS["on_surface_variant"])
            return

        if event_type == "task_resumed":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.set_paused(video_id, False)
            self.playlist_view.mark_status(video_id, "DOWNLOADING", color=TOKENS["primary"])
            return

        if event_type == "task_completed":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.update_progress(video_id, 100.0)
            self.playlist_view.mark_status(video_id, "DOWNLOADED", color="#70d48a")
            self._store_history("completed", event, error_message="", error_code="")
            return

        if event_type == "task_failed":
            video_id = str(event.get("video_id", ""))
            error_code = str(event.get("error_code", "UNKNOWN"))
            error_text = str(event.get("error", "Unknown error"))
            self.playlist_view.mark_status(video_id, "QUEUED", color=TOKENS["on_surface_variant"])
            self._store_history("failed", event, error_message=error_text, error_code=error_code)
            return

        if event_type == "task_cancelled":
            video_id = str(event.get("video_id", ""))
            self.playlist_view.mark_status(video_id, "QUEUED", color=TOKENS["on_surface_variant"])
            self._store_history("cancelled", event, error_message="Cancelled by user.", error_code="CANCELLED")
            return

        if event_type == "overall_progress":
            percent = float(event.get("percent", 0.0))
            self.overall_progress.set(max(0.0, min(1.0, percent / 100.0)))
            self.global_progress_label.configure(text=f"GLOBAL PROGRESS  {percent:.1f}%")
            return

        if event_type == "batch_finished":
            completed = int(event.get("completed", 0))
            failed = int(event.get("failed", 0))
            cancelled = int(event.get("cancelled", 0))
            self.transfer_status.configure(text="Status: Ready to download", text_color=TOKENS["red"])
            self.init_download_btn.configure(state="normal")
            self.queue_status.configure(text="AWAITING TASK QUEUE...  0 KB/S")
            self.ready_status_label.configure(text="● STATUS: READY")
            self._notify_completion(completed, failed, cancelled)
            self._refresh_history_table()
            self._refresh_status_bar()
            return

    def _store_history(self, status: str, event: dict, error_message: str, error_code: str) -> None:
        playlist_title = self._playlist_info.title if self._playlist_info else "Unknown Source"
        source_platform = self._playlist_info.source_platform if self._playlist_info else "unknown"
        source_kind = self._playlist_info.source_kind if self._playlist_info else "direct"
        self._database.add_entry(
            HistoryEntry(
                playlist_title=playlist_title,
                video_title=str(event.get("title", "Unknown Video")),
                video_url=str(event.get("url", "")),
                source_platform=source_platform,
                source_kind=source_kind,
                status=status,
                quality=self.quality_var.get(),
                file_format=self.format_var.get(),
                output_path=str(event.get("output_path", "")),
                file_size_bytes=int(event.get("file_size", 0) or 0),
                error_code=error_code,
                error_message=error_message,
            )
        )

    def _refresh_history_table(self) -> None:
        for child in self.history_list.winfo_children():
            child.destroy()

        rows = self._database.list_recent(limit=500)
        total = len(rows)
        success = sum(1 for r in rows if r.get("status") == "completed")
        failed = sum(1 for r in rows if r.get("status") == "failed")
        saved_bytes = sum(int(r.get("file_size_bytes") or 0) for r in rows)

        self.history_stats[0].configure(text=str(total))
        self.history_stats[1].configure(text=str(success), text_color="#70d48a")
        self.history_stats[2].configure(text=str(failed), text_color=TOKENS["red"])
        self.history_stats[3].configure(text=self._format_bytes(saved_bytes))

        show_rows = rows[:5]
        for idx, row in enumerate(show_rows):
            bg = TOKENS["surface_container_low"] if idx % 2 else TOKENS["surface_container_lowest"]
            line = ctk.CTkFrame(self.history_list, fg_color=bg, corner_radius=8)
            line.grid(row=idx, column=0, sticky="ew", pady=(0, 6))
            line.grid_columnconfigure(1, weight=1)

            raw_ts = str(row.get("downloaded_at", "") or "")
            try:
                pretty_ts = datetime.fromisoformat(raw_ts).strftime("%Y-%m-%d  %H:%M:%S")
            except ValueError:
                pretty_ts = raw_ts

            ctk.CTkLabel(line, text=pretty_ts, text_color=TOKENS["on_surface_variant"], font=("Consolas", 10)).grid(
                row=0, column=0, padx=8, pady=8, sticky="w"
            )
            ctk.CTkLabel(line, text=row.get("video_title", ""), text_color=TOKENS["on_surface"], font=("Inter", 11, "bold"), anchor="w").grid(
                row=0, column=1, padx=8, pady=8, sticky="ew"
            )

            status = str(row.get("status", "")).upper()
            if status == "COMPLETED":
                status_text = "● SUCCESS"
                status_bg = "#133020"
                status_color = "#70d48a"
            else:
                status_text = "● FAILED" if status == "FAILED" else "● CANCELLED"
                status_bg = "#3a1717"
                status_color = TOKENS["red"]

            ctk.CTkLabel(
                line,
                text=status_text,
                fg_color=status_bg,
                text_color=status_color,
                corner_radius=10,
                padx=8,
                pady=2,
                font=("Inter", 10, "bold"),
            ).grid(row=0, column=2, padx=8, pady=8)

            err_code = row.get("error_code") or "---"
            ctk.CTkLabel(line, text=err_code, text_color=TOKENS["red"], font=("Consolas", 10)).grid(row=0, column=3, padx=8, pady=8)

            action_txt = "📁" if status == "COMPLETED" else "↻"
            ctk.CTkButton(
                line,
                text=action_txt,
                width=34,
                fg_color=TOKENS["surface_container_high"],
                hover_color=TOKENS["surface_bright"],
                corner_radius=8,
                command=lambda r=row: self._history_action(r),
            ).grid(row=0, column=4, padx=8, pady=8)

        self.history_page_label.configure(text=f"Showing 1-{len(show_rows)} of {total} records")

    def _history_action(self, row: dict) -> None:
        status = str(row.get("status", ""))
        if status == "completed":
            path = row.get("output_path")
            if path and Path(path).exists():
                os.startfile(str(Path(path).parent))
        else:
            messagebox.showinfo("Retry", "Retry action placeholder for failed item.")

    def _clear_history(self) -> None:
        if not messagebox.askyesno("Confirm", "Clear all history records?"):
            return
        self._database.clear_history()
        self._refresh_history_table()

    def _apply_settings_values(self, values: dict) -> None:
        self.quality_var.set(values.get("quality", self.quality_var.get()))
        self.format_var.set(values.get("format", self.format_var.get()))
        self.parallel_var.set(int(values.get("parallel", self.parallel_var.get())))
        self.output_dir_var.set(values.get("output_dir", self.output_dir_var.get()))
        self.settings_view.set_output_dir(self.output_dir_var.get())
        self.auto_subfolder_var.set(bool(values.get("auto_subfolder", self.auto_subfolder_var.get())))
        self.scope_mode_var.set(str(values.get("scope_mode", self.scope_mode_var.get())))
        self.max_items_var.set(int(values.get("max_items", self.max_items_var.get())))
        self.video_only_var.set(bool(values.get("video_only", self.video_only_var.get())))
        self.cookies_mode_var.set(str(values.get("cookies_mode", self.cookies_mode_var.get())))
        self.cookies_browser_var.set(str(values.get("cookies_browser", self.cookies_browser_var.get())))
        self.cookies_file_var.set(str(values.get("cookies_file", self.cookies_file_var.get())))
        self.settings_view.set_cookies_file(self.cookies_file_var.get())
        self._sound_enabled = bool(values.get("sound", self._sound_enabled))
        appearance = "dark" if bool(values.get("dark_mode", True)) else "light"
        self._set_appearance(appearance)
        self._save_preferences()

    def _pick_output_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(Path.home()))
        if selected:
            self.output_dir_var.set(selected)
            self.settings_view.set_output_dir(selected)
            self._save_preferences()
            self._refresh_status_bar()

    def _pick_cookies_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select cookies file",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if selected:
            self.cookies_file_var.set(selected)
            self.settings_view.set_cookies_file(selected)
            self._save_preferences()

    def _toggle_theme(self) -> None:
        mode = "light" if ctk.get_appearance_mode().lower() == "dark" else "dark"
        self._set_appearance(mode)
        self.settings_view.set_dark_mode(mode == "dark")
        self._save_preferences()

    def _refresh_status_bar(self) -> None:
        try:
            socket.create_connection(("www.google.com", 443), timeout=1.5).close()
            network_text = "NETWORK: CONNECTED"
        except OSError:
            network_text = "NETWORK: OFFLINE"

        disk = shutil.disk_usage(Path(self.output_dir_var.get() or Path.home()))
        free_gb = disk.free / (1024 ** 3)
        storage_text = f"STORAGE: {free_gb:.1f} GB FREE"

        self.network_status_label.configure(text=network_text)
        self.storage_status_label.configure(text=storage_text)
        self.ready_status_label.configure(text="● STATUS: READY")

    def _set_appearance(self, mode: str) -> None:
        mode = "light" if mode.lower() == "light" else "dark"
        ctk.set_appearance_mode(mode)

    def _save_preferences(self) -> None:
        pref = AppPreferences(
            last_output_dir=self.output_dir_var.get().strip(),
            notifications_enabled=self._notification_enabled,
            sound_enabled=self._sound_enabled,
            auto_subfolder=bool(self.auto_subfolder_var.get()),
            parallel_downloads=max(1, min(3, int(self.parallel_var.get()))),
            quality=self.quality_var.get(),
            file_format=self.format_var.get(),
            appearance_mode=ctk.get_appearance_mode().lower(),
            scope_mode=self.scope_mode_var.get().strip() or "auto",
            max_items=max(1, min(500, int(self.max_items_var.get()))),
            video_only=bool(self.video_only_var.get()),
            cookies_mode=self.cookies_mode_var.get().strip() or "auto",
            cookies_browser=self.cookies_browser_var.get().strip() or "chrome",
            cookies_file=self.cookies_file_var.get().strip(),
        )
        self._preferences = pref
        self._preferences_store.save(pref)

    def _notify_completion(self, completed: int, failed: int, cancelled: int) -> None:
        if self._notification_enabled and self._toaster:
            try:
                self._toaster.show_toast(
                    "Kinetic Downloader",
                    f"Completed: {completed}, Failed: {failed}, Cancelled: {cancelled}",
                    duration=5,
                    threaded=True,
                )
            except Exception:
                pass
        if self._sound_enabled:
            if winsound:
                try:
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                except Exception:
                    self.bell()
            else:
                self.bell()

    def _on_close(self) -> None:
        if self._download_manager.is_running:
            if not messagebox.askyesno("Exit", "Downloads are still running. Exit anyway?"):
                return
        self._save_preferences()
        self._download_manager.shutdown()
        self._analysis_executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        bad_chars = '<>:"/\\|?*'
        cleaned = "".join("_" if ch in bad_chars else ch for ch in name).strip().rstrip(".")
        return cleaned or "Media Collection"

    @staticmethod
    def _format_bytes(num: float) -> str:
        value = float(max(0.0, num))
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        while value >= 1024.0 and idx < len(units) - 1:
            value /= 1024.0
            idx += 1
        return f"{value:.1f} {units[idx]}"

    @staticmethod
    def _get_app_data_dir() -> Path:
        base = os.getenv("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / ".local"
        target = root / "YouTubePlaylistDownloader"
        target.mkdir(parents=True, exist_ok=True)
        return target
