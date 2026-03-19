from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class HistoryEntry:
    playlist_title: str
    video_title: str
    video_url: str
    status: str
    quality: str
    file_format: str
    output_path: str
    file_size_bytes: int
    error_code: str
    error_message: str


class HistoryDatabase:
    def __init__(self, db_path: Path, max_records: int = 500) -> None:
        self._db_path = db_path
        self._max_records = max_records
        self._lock = threading.Lock()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS download_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        playlist_title TEXT NOT NULL,
                        video_title TEXT NOT NULL,
                        video_url TEXT NOT NULL,
                        status TEXT NOT NULL,
                        quality TEXT NOT NULL,
                        file_format TEXT NOT NULL,
                        output_path TEXT,
                        file_size_bytes INTEGER NOT NULL DEFAULT 0,
                        error_code TEXT NOT NULL DEFAULT '',
                        error_message TEXT,
                        downloaded_at TEXT NOT NULL
                    )
                    """
                )
                columns = {row[1] for row in conn.execute("PRAGMA table_info(download_history)").fetchall()}
                if "error_code" not in columns:
                    conn.execute("ALTER TABLE download_history ADD COLUMN error_code TEXT NOT NULL DEFAULT ''")
                conn.commit()

    def add_entry(self, entry: HistoryEntry) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO download_history (
                        playlist_title,
                        video_title,
                        video_url,
                        status,
                        quality,
                        file_format,
                        output_path,
                        file_size_bytes,
                        error_code,
                        error_message,
                        downloaded_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.playlist_title,
                        entry.video_title,
                        entry.video_url,
                        entry.status,
                        entry.quality,
                        entry.file_format,
                        entry.output_path,
                        max(0, int(entry.file_size_bytes)),
                        entry.error_code,
                        entry.error_message,
                        timestamp,
                    ),
                )
                self._prune_locked(conn)
                conn.commit()

    def _prune_locked(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM download_history
            WHERE id NOT IN (
                SELECT id
                FROM download_history
                ORDER BY id DESC
                LIMIT ?
            )
            """,
            (self._max_records,),
        )

    def list_recent(self, limit: int = 100) -> list[dict[str, str]]:
        safe_limit = max(1, min(limit, self._max_records))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT
                        playlist_title,
                        video_title,
                        video_url,
                        status,
                        quality,
                        file_format,
                        output_path,
                        file_size_bytes,
                        error_code,
                        error_message,
                        downloaded_at
                    FROM download_history
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()

        return [dict(row) for row in rows]

    def clear_history(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM download_history")
                conn.commit()
