from __future__ import annotations

import os
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


class DownloadCancelled(Exception):
    """Raised when the user cancels an in-flight download."""


@dataclass(slots=True)
class DownloadTask:
    video_id: str
    title: str
    url: str
    duration_seconds: int


@dataclass(slots=True)
class DownloadOptions:
    quality: str
    file_format: str
    output_dir: Path
    parallel_downloads: int = 1
    max_retries: int = 3


@dataclass(slots=True)
class TaskControl:
    pause_event: threading.Event = field(default_factory=threading.Event)
    cancel_event: threading.Event = field(default_factory=threading.Event)


EventCallback = Callable[[dict[str, Any]], None]


class DownloadManager:
    """Thread-safe yt-dlp batch manager with pause/resume/cancel support."""

    def __init__(self, on_event: EventCallback) -> None:
        self._on_event = on_event
        self._lock = threading.Lock()

        self._controls: dict[str, TaskControl] = {}
        self._task_progress: dict[str, float] = {}
        self._task_meta: dict[str, DownloadTask] = {}

        self._executor: ThreadPoolExecutor | None = None
        self._watcher_thread: threading.Thread | None = None

        self._running = False
        self._playlist_title = ""
        self._download_options: DownloadOptions | None = None
        self._counters = {"completed": 0, "failed": 0, "cancelled": 0}
        self._global_cooldown_until = 0.0
        self._rate_limit_hits = 0

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start_batch(self, playlist_title: str, tasks: list[DownloadTask], options: DownloadOptions) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("A download batch is already running.")
            if not tasks:
                raise ValueError("No tasks provided.")

            self._running = True
            self._playlist_title = playlist_title
            self._download_options = options
            self._controls = {task.video_id: TaskControl() for task in tasks}
            self._task_progress = {task.video_id: 0.0 for task in tasks}
            self._task_meta = {task.video_id: task for task in tasks}
            self._counters = {"completed": 0, "failed": 0, "cancelled": 0}
            self._global_cooldown_until = 0.0
            self._rate_limit_hits = 0

            worker_count = max(1, min(3, int(options.parallel_downloads)))
            self._executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="ydlp-worker")

        self._emit(
            {
                "type": "batch_started",
                "playlist_title": playlist_title,
                "total_tasks": len(tasks),
                "parallel_downloads": worker_count,
            }
        )

        futures: list[Future[dict[str, Any]]] = []
        assert self._executor is not None
        for task in tasks:
            self._emit(
                {
                    "type": "task_queued",
                    "video_id": task.video_id,
                    "title": task.title,
                }
            )
            future = self._executor.submit(self._download_single, task)
            futures.append(future)

        self._watcher_thread = threading.Thread(
            target=self._watch_batch,
            args=(futures,),
            daemon=True,
            name="download-watcher",
        )
        self._watcher_thread.start()

    def pause_all(self) -> None:
        with self._lock:
            for control in self._controls.values():
                control.pause_event.set()
        self._emit({"type": "batch_paused"})

    def resume_all(self) -> None:
        with self._lock:
            for control in self._controls.values():
                control.pause_event.clear()
        self._emit({"type": "batch_resumed"})

    def cancel_all(self) -> None:
        with self._lock:
            for control in self._controls.values():
                control.cancel_event.set()
        self._emit({"type": "batch_cancel_requested"})

    def pause_task(self, video_id: str) -> None:
        with self._lock:
            control = self._controls.get(video_id)
            if control:
                control.pause_event.set()

    def resume_task(self, video_id: str) -> None:
        with self._lock:
            control = self._controls.get(video_id)
            if control:
                control.pause_event.clear()

    def cancel_task(self, video_id: str) -> None:
        with self._lock:
            control = self._controls.get(video_id)
            if control:
                control.cancel_event.set()

    def shutdown(self) -> None:
        self.cancel_all()
        with self._lock:
            executor = self._executor
            self._executor = None
            self._running = False

        if executor:
            executor.shutdown(wait=False, cancel_futures=True)

    def _watch_batch(self, futures: list[Future[dict[str, Any]]]) -> None:
        results: list[dict[str, Any]] = []
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = {
                    "status": "failed",
                    "video_id": "",
                    "title": "Unknown",
                    "url": "",
                    "file_size": 0,
                    "output_path": "",
                    "error": f"Unexpected worker failure: {exc}",
                }
            results.append(result)

        with self._lock:
            self._running = False
            executor = self._executor
            self._executor = None

        if executor:
            executor.shutdown(wait=False, cancel_futures=False)

        completed = sum(1 for r in results if r["status"] == "completed")
        failed = sum(1 for r in results if r["status"] == "failed")
        cancelled = sum(1 for r in results if r["status"] == "cancelled")

        self._emit(
            {
                "type": "batch_finished",
                "playlist_title": self._playlist_title,
                "total_tasks": len(results),
                "completed": completed,
                "failed": failed,
                "cancelled": cancelled,
            }
        )

    def _download_single(self, task: DownloadTask) -> dict[str, Any]:
        options = self._download_options
        if options is None:
            return {
                "status": "failed",
                "video_id": task.video_id,
                "title": task.title,
                "url": task.url,
                "file_size": 0,
                "output_path": "",
                "error": "Downloader not initialized.",
            }

        control = self._controls[task.video_id]
        worker_state: dict[str, Any] = {
            "paused_sent": False,
            "output_path": "",
            "downloaded": 0,
            "total": 0,
        }

        def progress_hook(data: dict[str, Any]) -> None:
            if control.cancel_event.is_set():
                raise DownloadCancelled("Cancelled by user.")

            if control.pause_event.is_set():
                if not worker_state["paused_sent"]:
                    worker_state["paused_sent"] = True
                    self._emit(
                        {
                            "type": "task_paused",
                            "video_id": task.video_id,
                            "title": task.title,
                        }
                    )

                while control.pause_event.is_set():
                    if control.cancel_event.is_set():
                        raise DownloadCancelled("Cancelled by user.")
                    time.sleep(0.20)

                worker_state["paused_sent"] = False
                self._emit(
                    {
                        "type": "task_resumed",
                        "video_id": task.video_id,
                        "title": task.title,
                    }
                )

            status = data.get("status")
            if status == "downloading":
                total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
                downloaded = int(data.get("downloaded_bytes") or 0)
                percent = self._calc_percent(downloaded, total, data.get("_percent_str", ""))
                speed = float(data.get("speed") or 0)
                eta = int(data.get("eta") or 0)

                worker_state["downloaded"] = downloaded
                worker_state["total"] = total
                if data.get("filename"):
                    worker_state["output_path"] = str(data.get("filename"))

                self._set_task_progress(task.video_id, percent)
                self._emit(
                    {
                        "type": "task_progress",
                        "video_id": task.video_id,
                        "title": task.title,
                        "downloaded": downloaded,
                        "total": total,
                        "remaining": max(0, total - downloaded) if total else 0,
                        "percent": percent,
                        "speed": speed,
                        "eta": eta,
                    }
                )
            elif status == "finished":
                if data.get("filename"):
                    worker_state["output_path"] = str(data.get("filename"))
                self._emit(
                    {
                        "type": "task_processing",
                        "video_id": task.video_id,
                        "title": task.title,
                    }
                )

        def postprocessor_hook(data: dict[str, Any]) -> None:
            if data.get("status") != "finished":
                return
            info = data.get("info_dict") or {}
            if info.get("filepath"):
                worker_state["output_path"] = str(info.get("filepath"))

        max_retries = max(1, int(options.max_retries))

        self._emit(
            {
                "type": "task_started",
                "video_id": task.video_id,
                "title": task.title,
            }
        )

        last_error = ""
        for attempt in range(1, max_retries + 1):
            self._wait_for_global_cooldown(control, task)

            if control.cancel_event.is_set():
                self._set_task_progress(task.video_id, 100.0)
                self._emit(
                    {
                        "type": "task_cancelled",
                        "video_id": task.video_id,
                        "title": task.title,
                        "url": task.url,
                    }
                )
                return {
                    "status": "cancelled",
                    "video_id": task.video_id,
                    "title": task.title,
                    "url": task.url,
                    "file_size": 0,
                    "output_path": worker_state["output_path"],
                    "error": "Cancelled by user.",
                }

            ydl_options = self._build_ydl_options(options, progress_hook, postprocessor_hook)
            try:
                with YoutubeDL(cast(Any, ydl_options)) as ydl:
                    ydl.download([task.url])
                last_error = ""
                break
            except DownloadCancelled:
                self._set_task_progress(task.video_id, 100.0)
                self._emit(
                    {
                        "type": "task_cancelled",
                        "video_id": task.video_id,
                        "title": task.title,
                        "url": task.url,
                    }
                )
                return {
                    "status": "cancelled",
                    "video_id": task.video_id,
                    "title": task.title,
                    "url": task.url,
                    "file_size": 0,
                    "output_path": worker_state["output_path"],
                    "error": "Cancelled by user.",
                }
            except DownloadError as exc:
                last_error = str(exc)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)

            error_code, reason = self._classify_error(last_error)
            if error_code == "RATE_LIMIT":
                cooldown_seconds = self._raise_rate_limit_cooldown()
                self._emit(
                    {
                        "type": "global_cooldown",
                        "seconds": cooldown_seconds,
                        "reason": reason,
                    }
                )

            retriable = self._is_retryable_error(last_error)
            if attempt < max_retries and retriable and not control.cancel_event.is_set():
                delay_seconds = min(20.0, 2.0 ** (attempt - 1))
                self._emit(
                    {
                        "type": "task_retrying",
                        "video_id": task.video_id,
                        "title": task.title,
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "delay_seconds": delay_seconds,
                        "error_code": error_code,
                        "error": reason,
                    }
                )

                sleep_end = time.monotonic() + delay_seconds
                while time.monotonic() < sleep_end:
                    if control.cancel_event.is_set():
                        self._set_task_progress(task.video_id, 100.0)
                        self._emit(
                            {
                                "type": "task_cancelled",
                                "video_id": task.video_id,
                                "title": task.title,
                                "url": task.url,
                            }
                        )
                        return {
                            "status": "cancelled",
                            "video_id": task.video_id,
                            "title": task.title,
                            "url": task.url,
                            "file_size": 0,
                            "output_path": worker_state["output_path"],
                            "error": "Cancelled by user.",
                        }
                    time.sleep(0.2)
                continue

            self._set_task_progress(task.video_id, 100.0)
            self._emit(
                {
                    "type": "task_failed",
                    "video_id": task.video_id,
                    "title": task.title,
                    "url": task.url,
                    "error_code": error_code,
                    "error": reason,
                    "attempts": attempt,
                }
            )
            return {
                "status": "failed",
                "video_id": task.video_id,
                "title": task.title,
                "url": task.url,
                "file_size": 0,
                "output_path": worker_state["output_path"],
                "error_code": error_code,
                "error": reason,
            }

        if last_error:
            error_code, reason = self._classify_error(last_error)
            self._set_task_progress(task.video_id, 100.0)
            self._emit(
                {
                    "type": "task_failed",
                    "video_id": task.video_id,
                    "title": task.title,
                    "url": task.url,
                    "error_code": error_code,
                    "error": reason,
                    "attempts": max_retries,
                }
            )
            return {
                "status": "failed",
                "video_id": task.video_id,
                "title": task.title,
                "url": task.url,
                "file_size": 0,
                "output_path": worker_state["output_path"],
                "error_code": error_code,
                "error": reason,
            }

        output_path_str = str(worker_state["output_path"] or "")
        final_path = Path(output_path_str) if output_path_str else None
        file_size = 0
        if final_path and final_path.exists() and final_path.is_file():
            try:
                file_size = final_path.stat().st_size
            except OSError:
                file_size = 0

        self._set_task_progress(task.video_id, 100.0)
        self._emit(
            {
                "type": "task_completed",
                "video_id": task.video_id,
                "title": task.title,
                "url": task.url,
                "output_path": str(final_path) if final_path else "",
                "file_size": file_size,
            }
        )
        return {
            "status": "completed",
            "video_id": task.video_id,
            "title": task.title,
            "url": task.url,
            "file_size": file_size,
            "output_path": str(final_path) if final_path else "",
            "error": "",
        }

    def _set_task_progress(self, video_id: str, percent: float) -> None:
        with self._lock:
            self._task_progress[video_id] = max(0.0, min(100.0, percent))
            if not self._task_progress:
                return
            snapshot = dict(self._task_progress)
            overall = sum(snapshot.values()) / len(snapshot)

        completed_tasks = sum(1 for p in snapshot.values() if p >= 100.0)
        total_tasks = len(snapshot)

        self._emit(
            {
                "type": "overall_progress",
                "percent": overall,
                "completed_tasks": completed_tasks,
                "total_tasks": total_tasks,
            }
        )

    def _build_ydl_options(
        self,
        options: DownloadOptions,
        progress_hook: Callable[[dict[str, Any]], None],
        postprocessor_hook: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        fmt = options.file_format.upper()
        quality = options.quality.upper()
        height_map = {"1080P": 1080, "720P": 720, "480P": 480, "360P": 360}

        ydl_options: dict[str, Any] = {
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
            "continuedl": True,
            "windowsfilenames": True,
            "outtmpl": str(options.output_dir / "%(title).200B [%(id)s].%(ext)s"),
            "progress_hooks": [progress_hook],
            "postprocessor_hooks": [postprocessor_hook],
            "socket_timeout": 30,
        }

        ffmpeg_path = self._resolve_ffmpeg_path()
        if ffmpeg_path:
            ydl_options["ffmpeg_location"] = ffmpeg_path

        audio_mode = quality == "AUDIO ONLY" or fmt in {"MP3", "M4A"}
        if audio_mode:
            ydl_options["format"] = "bestaudio/best"
            ydl_options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3" if fmt == "MP3" else "m4a",
                    "preferredquality": "192",
                }
            ]
        else:
            max_height = height_map.get(quality, 720)
            ydl_options["format"] = (
                f"bestvideo[height<={max_height}]+bestaudio/"
                f"best[height<={max_height}]/best"
            )
            ydl_options["merge_output_format"] = "mkv" if fmt == "MKV" else "mp4"

        return ydl_options

    @staticmethod
    def _resolve_ffmpeg_path() -> str:
        try:
            import imageio_ffmpeg  # type: ignore

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _calc_percent(downloaded: int, total: int, percent_text: str) -> float:
        if total > 0:
            return (downloaded / total) * 100.0

        stripped = percent_text.replace("%", "").strip()
        try:
            return float(stripped)
        except ValueError:
            return 0.0

    @staticmethod
    def _classify_error(raw_message: str) -> tuple[str, str]:
        message = raw_message.strip() or "Unknown download error."
        lower = message.lower()

        if "unsupported url" in lower:
            return "INVALID_URL", "Invalid URL for this video. Please verify the link is a YouTube watch URL."
        if "private video" in lower or "private" in lower:
            return "PRIVATE_VIDEO", "This video is private and cannot be downloaded by anonymous requests."
        if "age" in lower and "restricted" in lower:
            return "AGE_RESTRICTED", "This video is age-restricted and requires an authenticated session."
        if "sign in to confirm your age" in lower:
            return "AGE_CONFIRMATION", "Age confirmation required by YouTube. Sign-in credentials are needed."
        if "members-only" in lower or "members only" in lower:
            return (
                "MEMBERS_ONLY",
                "This video is members-only and is not accessible without membership credentials.",
            )
        if "this video is unavailable" in lower:
            return "UNAVAILABLE", "The video is unavailable in your region/account or has been removed."
        if "copyright" in lower:
            return "COPYRIGHT_BLOCK", "The video appears blocked by copyright restrictions in your region."
        if "http error 403" in lower or "forbidden" in lower:
            return (
                "HTTP_403",
                "Access denied (HTTP 403). The stream may require authentication or be geo-blocked.",
            )
        if "http error 404" in lower or "not found" in lower:
            return "HTTP_404", "Resource not found (HTTP 404). The video may have been removed."
        if "429" in lower or "too many requests" in lower:
            return "RATE_LIMIT", "Rate-limited by YouTube (HTTP 429). Wait a few minutes and retry."
        if "no space left" in lower or "disk full" in lower:
            return "DISK_FULL", "Download failed because the disk is full. Free disk space and retry."
        if "permission denied" in lower or "access is denied" in lower:
            return (
                "PERMISSION_DENIED",
                "Permission denied while writing output files. Choose another folder or run with proper rights.",
            )
        if "ffmpeg" in lower and "not found" in lower:
            return (
                "FFMPEG_MISSING",
                "FFmpeg is missing, so merging/conversion could not run. Rebuild app with bundled ffmpeg.",
            )
        if "timed out" in lower or "network" in lower or "connection" in lower:
            return "NETWORK_ERROR", "Network issue detected. Check connection/VPN and retry."

        return "UNKNOWN", message

    def _wait_for_global_cooldown(self, control: TaskControl, task: DownloadTask) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                remaining = self._global_cooldown_until - now
            if remaining <= 0:
                return
            self._emit(
                {
                    "type": "task_waiting_cooldown",
                    "video_id": task.video_id,
                    "title": task.title,
                    "seconds": max(1, int(remaining)),
                }
            )
            if control.cancel_event.is_set():
                return
            time.sleep(min(0.5, remaining))

    def _raise_rate_limit_cooldown(self) -> int:
        with self._lock:
            self._rate_limit_hits += 1
            seconds = min(300, 15 * (2 ** max(0, self._rate_limit_hits - 1)))
            self._global_cooldown_until = max(self._global_cooldown_until, time.monotonic() + seconds)
            return seconds

    @staticmethod
    def _is_retryable_error(raw_message: str) -> bool:
        lower = raw_message.lower()
        retry_keywords = (
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "network",
            "http error 5",
            "503",
            "502",
            "429",
            "too many requests",
            "remote end closed connection",
            "ssl",
            "incomplete read",
            "chunkedencodingerror",
        )
        non_retry_keywords = (
            "private",
            "age-restricted",
            "sign in",
            "unsupported url",
            "not found",
            "permission denied",
            "access is denied",
            "disk is full",
            "no space left",
            "copyright",
            "members-only",
        )

        if any(word in lower for word in non_retry_keywords):
            return False
        return any(word in lower for word in retry_keywords)

    def _emit(self, event: dict[str, Any]) -> None:
        try:
            self._on_event(event)
        except Exception:
            # UI callback failures should not crash worker threads.
            pass
