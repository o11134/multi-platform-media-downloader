from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import customtkinter as ctk
import requests
from PIL import Image

from core.analyzer import PlaylistVideo, format_duration


SURFACE = "#131313"
SURFACE_LOW = "#1b1b1c"
SURFACE_HIGH = "#2a2a2a"
SURFACE_LOWEST = "#0e0e0e"
SURFACE_HIGHEST = "#353535"
ON_SURFACE = "#e5e2e1"
ON_SURFACE_VARIANT = "#ebbbb4"
MUTED = "#474747"
RED = "#FF0000"
PRIMARY = "#ffb4a8"
GREEN = "#70d48a"

THUMB_LARGE_W = 120
THUMB_LARGE_H = 68
THUMB_ROW_W = 80
THUMB_ROW_H = 45


class VideoRow(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        index: int,
        video: PlaylistVideo,
        on_toggle: Callable[[str, bool], None],
        on_pause_resume: Callable[[str], None],
        on_copy_link: Callable[[str], None],
        background: str,
    ) -> None:
        super().__init__(master, fg_color=background, corner_radius=0)
        self.video = video
        self._on_toggle = on_toggle
        self._on_pause_resume = on_pause_resume
        self._on_copy_link = on_copy_link
        self._paused = False
        self._thumb_ref: ctk.CTkImage | None = None

        self.grid_columnconfigure(0, weight=0, minsize=56)
        self.grid_columnconfigure(1, weight=1, minsize=440)
        self.grid_columnconfigure(2, weight=0, minsize=110)
        self.grid_columnconfigure(3, weight=0, minsize=120)

        self.selected_var = ctk.BooleanVar(value=True)

        id_col = ctk.CTkFrame(self, fg_color="transparent")
        id_col.grid(row=0, column=0, padx=(10, 8), pady=8, sticky="nsew")
        id_col.grid_columnconfigure(1, weight=0)

        self.checkbox = ctk.CTkCheckBox(
            id_col,
            text="",
            variable=self.selected_var,
            command=self._emit_toggle,
            fg_color=RED,
            hover_color="#ff5540",
            width=18,
        )
        self.checkbox.grid(row=0, column=0, padx=(0, 6), pady=0, sticky="w")

        ctk.CTkLabel(
            id_col,
            text=f"{index}",
            text_color=MUTED,
            font=("Consolas", 11),
        ).grid(row=0, column=1, sticky="w")

        content_col = ctk.CTkFrame(self, fg_color="transparent")
        content_col.grid(row=0, column=1, padx=(0, 8), pady=6, sticky="nsew")
        content_col.grid_columnconfigure(1, weight=1)
        content_col.grid_rowconfigure(1, weight=0)

        thumb_shell = ctk.CTkFrame(
            content_col,
            fg_color=SURFACE_HIGHEST,
            corner_radius=4,
            width=THUMB_ROW_W,
            height=THUMB_ROW_H,
        )
        thumb_shell.grid(row=0, column=0, rowspan=2, padx=(0, 10), pady=0, sticky="w")
        thumb_shell.grid_propagate(False)

        self.thumbnail_label = ctk.CTkLabel(
            thumb_shell,
            text="",
            width=THUMB_ROW_W,
            height=THUMB_ROW_H,
            corner_radius=4,
            fg_color=SURFACE_HIGHEST,
        )
        self.thumbnail_label.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")

        self.title_label = ctk.CTkLabel(
            content_col,
            text=video.title,
            text_color=ON_SURFACE,
            font=("Inter", 12, "bold"),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        self.title_label.grid(row=0, column=1, sticky="ew", pady=(0, 2))

        self.status_label = ctk.CTkLabel(
            content_col,
            text="QUEUED",
            text_color=ON_SURFACE_VARIANT,
            fg_color=SURFACE_HIGH,
            corner_radius=6,
            padx=8,
            pady=2,
            font=("Inter", 10, "bold"),
            anchor="w",
        )
        self.status_label.grid(row=1, column=1, sticky="w")

        self.inline_progress = ctk.CTkProgressBar(
            content_col,
            height=2,
            corner_radius=2,
            fg_color=SURFACE_HIGHEST,
            progress_color=RED,
        )
        self.inline_progress.grid(row=2, column=1, pady=(4, 0), sticky="ew")
        self.inline_progress.set(0.0)
        self.inline_progress.grid_remove()

        ctk.CTkLabel(
            self,
            text=format_duration(video.duration_seconds),
            text_color=ON_SURFACE_VARIANT,
            font=("Consolas", 11),
            anchor="e",
        ).grid(row=0, column=2, padx=(8, 8), pady=8, sticky="e")

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=0, column=3, padx=(0, 8), pady=8, sticky="e")

        self.pause_btn = ctk.CTkButton(
            actions,
            text="⏸",
            width=34,
            height=30,
            fg_color=SURFACE_HIGH,
            hover_color=SURFACE_HIGHEST,
            corner_radius=15,
            command=self._toggle_pause,
        )
        self.pause_btn.grid(row=0, column=0, padx=(0, 6), sticky="e")

        ctk.CTkButton(
            actions,
            text="🔗",
            width=34,
            height=30,
            fg_color=SURFACE_HIGH,
            hover_color=SURFACE_HIGHEST,
            corner_radius=15,
            command=lambda: self._on_copy_link(self.video.video_id),
        ).grid(row=0, column=1, sticky="e")

    def _emit_toggle(self) -> None:
        self._on_toggle(self.video.video_id, self.selected_var.get())

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.configure(text="▶" if self._paused else "⏸")
        self._on_pause_resume(self.video.video_id)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self.pause_btn.configure(text="▶" if paused else "⏸")

    def set_thumbnail(self, image: ctk.CTkImage) -> None:
        self._thumb_ref = image
        self.thumbnail_label.configure(image=image)

    def set_status(self, status: str, color: str = ON_SURFACE_VARIANT) -> None:
        if "DOWNLOADED" in status.upper():
            self.status_label.configure(text="● DOWNLOADED", fg_color="transparent", text_color=GREEN)
            self.inline_progress.grid_remove()
            return
        if "DOWNLOADING" in status.upper():
            self.status_label.configure(text="DOWNLOADING", fg_color="transparent", text_color=PRIMARY)
            self.inline_progress.grid()
            return

        self.status_label.configure(text=status.upper(), fg_color=SURFACE_HIGH, text_color=color)

    def set_progress(self, percent: float) -> None:
        self.inline_progress.set(max(0.0, min(1.0, percent / 100.0)))
        if percent > 0:
            self.inline_progress.grid()

    def set_selected(self, selected: bool) -> None:
        self.selected_var.set(selected)
        self._emit_toggle()


class PlaylistView(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        cache_dir: Path,
        on_pause_resume: Callable[[str], None],
        on_copy_link: Callable[[str], None],
    ) -> None:
        super().__init__(master, fg_color=SURFACE, corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._thumb_executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="thumb-cache")
        self._thumb_generation = 0

        self._image_refs: dict[str, ctk.CTkImage] = {}
        self._rows: dict[str, VideoRow] = {}
        self._videos: dict[str, PlaylistVideo] = {}
        self._selection: dict[str, bool] = {}
        self._on_pause_resume = on_pause_resume
        self._on_copy_link = on_copy_link

        self.header = ctk.CTkFrame(self, fg_color=SURFACE_LOW, corner_radius=12)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.header.grid_columnconfigure(1, weight=1)

        self.header_thumb_shell = ctk.CTkFrame(
            self.header,
            fg_color=SURFACE_HIGHEST,
            corner_radius=8,
            width=120,
            height=90,
        )
        self.header_thumb_shell.grid(row=0, column=0, rowspan=2, padx=12, pady=12, sticky="w")
        self.header_thumb_shell.grid_propagate(False)

        self.header_thumb = ctk.CTkLabel(
            self.header_thumb_shell,
            text="",
            width=120,
            height=90,
            corner_radius=8,
            fg_color=SURFACE_HIGHEST,
        )
        self.header_thumb.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")

        self.badge = ctk.CTkLabel(
            self.header,
            text="0 VIDEOS",
            fg_color=RED,
            text_color="white",
            corner_radius=8,
            font=("Inter", 10, "bold"),
            padx=8,
            pady=3,
        )
        self.badge.grid(row=0, column=1, padx=(0, 10), pady=(12, 2), sticky="w")

        self.playlist_title = ctk.CTkLabel(
            self.header,
            text="No media source loaded",
            text_color=ON_SURFACE,
            font=("Inter", 20, "bold"),
            anchor="w",
        )
        self.playlist_title.grid(row=1, column=1, padx=(0, 10), pady=(0, 2), sticky="ew")

        self.meta = ctk.CTkLabel(
            self.header,
            text="Source - Duration - Pending Download",
            text_color=ON_SURFACE_VARIANT,
            font=("Inter", 11),
            anchor="w",
        )
        self.meta.grid(row=2, column=1, padx=(0, 10), pady=(0, 12), sticky="ew")

        controls = ctk.CTkFrame(self.header, fg_color="transparent")
        controls.grid(row=0, column=2, rowspan=3, padx=12, pady=12, sticky="e")

        self.select_all_btn = ctk.CTkButton(
            controls,
            text="SELECT ALL",
            fg_color=SURFACE_HIGH,
            hover_color=SURFACE_HIGHEST,
            corner_radius=8,
            command=self.select_all,
            width=110,
        )
        self.select_all_btn.grid(row=0, column=0, padx=(0, 6), sticky="e")

        self.deselect_all_btn = ctk.CTkButton(
            controls,
            text="DESELECT ALL",
            fg_color=SURFACE_HIGH,
            hover_color=SURFACE_HIGHEST,
            corner_radius=8,
            command=self.deselect_all,
            width=120,
        )
        self.deselect_all_btn.grid(row=0, column=1, padx=(0, 6), sticky="e")

        self.start_btn = ctk.CTkButton(
            controls,
            text="▼ START DOWNLOAD",
            fg_color=RED,
            hover_color="#ff5540",
            corner_radius=8,
            width=150,
        )
        self.start_btn.grid(row=0, column=2, sticky="e")

        table_header = ctk.CTkFrame(self, fg_color=SURFACE_LOW, corner_radius=8)
        table_header.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        table_header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(table_header, text="#", text_color=MUTED, font=("Inter", 10, "bold")).grid(row=0, column=0, padx=(12, 8), pady=8, sticky="w")
        ctk.CTkLabel(table_header, text="VIDEO TITLE", text_color=MUTED, font=("Inter", 10, "bold")).grid(row=0, column=1, pady=8, sticky="w")
        ctk.CTkLabel(table_header, text="DURATION", text_color=MUTED, font=("Inter", 10, "bold")).grid(row=0, column=2, padx=10, pady=8, sticky="e")
        ctk.CTkLabel(table_header, text="ACTIONS", text_color=MUTED, font=("Inter", 10, "bold")).grid(row=0, column=3, padx=(0, 12), pady=8, sticky="e")

        self.rows_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color=SURFACE,
            corner_radius=0,
            scrollbar_button_color=SURFACE_HIGHEST,
            scrollbar_button_hover_color="#393939",
        )
        self.rows_scroll.grid(row=2, column=0, sticky="nsew")
        self.rows_scroll.grid_columnconfigure(0, weight=1)

        self._empty_label = ctk.CTkLabel(
            self.rows_scroll,
            text="No media analyzed yet.",
            text_color=ON_SURFACE_VARIANT,
            font=("Inter", 12),
        )
        self._empty_label.grid(row=0, column=0, padx=12, pady=20, sticky="w")

        self._default_header_thumb = self._make_sized_image((120, 90), "#2d2d2d")
        self._default_row_thumb = self._make_sized_image((THUMB_ROW_W, THUMB_ROW_H), "#2d2d2d")
        self.header_thumb.configure(image=self._default_header_thumb)

    def destroy(self) -> None:
        self._thumb_executor.shutdown(wait=False, cancel_futures=True)
        super().destroy()

    @staticmethod
    def _make_sized_image(size: tuple[int, int], color: str) -> ctk.CTkImage:
        img = Image.new("RGB", size, color=color)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)

    def set_start_download_command(self, command: Callable[[], None]) -> None:
        self.start_btn.configure(command=command)

    def set_playlist_header(
        self,
        title: str,
        video_count: int,
        total_duration_seconds: int,
        source_platform: str = "unknown",
        source_kind: str = "direct",
    ) -> None:
        self.playlist_title.configure(text=title)
        self.badge.configure(text=f"{video_count} VIDEOS")
        platform_label = {
            "youtube": "YouTube",
            "instagram": "Instagram",
            "tiktok": "TikTok",
            "x": "X",
        }.get(source_platform.lower(), "Unknown")
        kind_label = "Profile" if source_kind == "profile" else "Collection" if source_kind == "collection" else "Direct Link"
        self.meta.configure(text=f"{platform_label} {kind_label} - {format_duration(total_duration_seconds)} - Pending Download")
        first = next(iter(self._videos.values()), None)
        if first and first.thumbnail_url:
            self._schedule_header_thumbnail(first.thumbnail_url)

    def set_videos(self, videos: list[PlaylistVideo]) -> None:
        self._thumb_generation += 1
        self._image_refs.clear()
        self.header_thumb.configure(image=self._default_header_thumb)

        for child in self.rows_scroll.winfo_children():
            child.destroy()

        self._rows.clear()
        self._videos = {v.video_id: v for v in videos}
        self._selection = {v.video_id: True for v in videos}

        if not videos:
            self._empty_label = ctk.CTkLabel(
                self.rows_scroll,
                text="No videos found.",
                text_color=ON_SURFACE_VARIANT,
                font=("Inter", 12),
            )
            self._empty_label.grid(row=0, column=0, padx=12, pady=20, sticky="w")
            return

        for idx, video in enumerate(videos, start=1):
            background = SURFACE_LOW if idx % 2 else SURFACE_LOWEST
            row = VideoRow(
                self.rows_scroll,
                index=idx,
                video=video,
                on_toggle=self._on_row_toggle,
                on_pause_resume=self._on_pause_resume,
                on_copy_link=self._on_copy_link,
                background=background,
            )
            row.grid(row=idx - 1, column=0, sticky="ew", padx=0, pady=0)
            row.set_thumbnail(self._default_row_thumb)
            self._rows[video.video_id] = row
            self._schedule_thumbnail(video, self._thumb_generation)

    def _on_row_toggle(self, video_id: str, selected: bool) -> None:
        self._selection[video_id] = selected

    def selected_video_ids(self) -> list[str]:
        return [k for k, v in self._selection.items() if v]

    def select_all(self) -> None:
        for row in self._rows.values():
            row.set_selected(True)

    def deselect_all(self) -> None:
        for row in self._rows.values():
            row.set_selected(False)

    def mark_status(self, video_id: str, status: str, color: str = ON_SURFACE_VARIANT) -> None:
        row = self._rows.get(video_id)
        if row:
            row.set_status(status, color=color)

    def update_progress(self, video_id: str, percent: float) -> None:
        row = self._rows.get(video_id)
        if row:
            row.set_progress(percent)

    def set_paused(self, video_id: str, paused: bool) -> None:
        row = self._rows.get(video_id)
        if row:
            row.set_paused(paused)

    def reset_progress(self) -> None:
        for row in self._rows.values():
            row.set_progress(0.0)
            row.set_status("QUEUED")

    def get_video(self, video_id: str) -> PlaylistVideo | None:
        return self._videos.get(video_id)

    def _schedule_thumbnail(self, video: PlaylistVideo, generation: int) -> None:
        if not video.thumbnail_url:
            return
        self._thumb_executor.submit(self._load_thumbnail_worker, video.video_id, video.thumbnail_url, generation)

    def _load_thumbnail_worker(self, video_id: str, url: str, generation: int) -> None:
        try:
            cache_path = self._cache_path_for_url(url)
            if not cache_path.exists():
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                cache_path.write_bytes(response.content)

            with Image.open(cache_path) as image:
                row_img = image.convert("RGB").resize((THUMB_ROW_W, THUMB_ROW_H), Image.Resampling.LANCZOS)

            def apply_image() -> None:
                self._apply_row_thumbnail(video_id, row_img, generation)

            self.after(0, apply_image)
        except Exception:
            pass

    def _apply_row_thumbnail(self, video_id: str, image: Image.Image, generation: int) -> None:
        if generation != self._thumb_generation:
            return
        row = self._rows.get(video_id)
        if not row:
            return
        thumb = ctk.CTkImage(light_image=image, dark_image=image, size=(THUMB_ROW_W, THUMB_ROW_H))
        self._image_refs[video_id] = thumb
        row.set_thumbnail(thumb)

    def _cache_path_for_url(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.jpg"

    def _schedule_header_thumbnail(self, url: str) -> None:
        self._thumb_executor.submit(self._load_header_thumbnail, url)

    def _load_header_thumbnail(self, url: str) -> None:
        try:
            cache_path = self._cache_path_for_url(url)
            if not cache_path.exists():
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                cache_path.write_bytes(response.content)

            with Image.open(cache_path) as image:
                header_img = image.convert("RGB").resize((120, 90), Image.Resampling.LANCZOS)

            def apply_image() -> None:
                thumb = ctk.CTkImage(light_image=header_img, dark_image=header_img, size=(120, 90))
                self._image_refs["header"] = thumb
                self.header_thumb.configure(image=thumb)

            self.after(0, apply_image)
        except Exception:
            pass
