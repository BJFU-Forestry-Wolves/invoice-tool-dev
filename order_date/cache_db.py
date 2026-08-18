from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .models import OCRPage, OCRTextBlock, SourceFile


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class CachedOCR:
    status: str
    pages: tuple[OCRPage, ...]
    error_code: str | None
    error_message: str | None


def _page_to_json(page: OCRPage) -> str:
    return json.dumps(
        {
            "page_index": page.page_index,
            "blocks": [
                {
                    "text": block.text,
                    "normalized_text": block.normalized_text,
                    "confidence": block.confidence,
                    "polygon": block.polygon,
                    "page_index": block.page_index,
                }
                for block in page.blocks
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _page_from_json(payload: str) -> OCRPage:
    value = json.loads(payload)
    blocks = tuple(
        OCRTextBlock(
            text=item["text"],
            normalized_text=item["normalized_text"],
            confidence=float(item["confidence"]),
            polygon=tuple(tuple(float(value) for value in point) for point in item["polygon"]),
            page_index=int(item["page_index"]),
        )
        for item in value["blocks"]
    )
    return OCRPage(page_index=int(value["page_index"]), blocks=blocks)


class OCRCache:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._initialize()

    def _initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    file_hash TEXT PRIMARY KEY,
                    absolute_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    modified_ns INTEGER NOT NULL,
                    extension TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS ocr_jobs (
                    file_hash TEXT NOT NULL,
                    engine_fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    error_code TEXT,
                    error_message TEXT,
                    processed_at TEXT NOT NULL,
                    PRIMARY KEY (file_hash, engine_fingerprint)
                );
                CREATE TABLE IF NOT EXISTS ocr_results (
                    file_hash TEXT NOT NULL,
                    engine_fingerprint TEXT NOT NULL,
                    page_index INTEGER NOT NULL,
                    ocr_payload_json TEXT NOT NULL,
                    PRIMARY KEY (file_hash, engine_fingerprint, page_index)
                );
                """
            )
            self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "OCRCache":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def get(self, file_hash: str, engine_fingerprint: str) -> CachedOCR | None:
        job = self.connection.execute(
            """SELECT status, error_code, error_message FROM ocr_jobs
               WHERE file_hash=? AND engine_fingerprint=?""",
            (file_hash, engine_fingerprint),
        ).fetchone()
        if job is None:
            return None
        rows = self.connection.execute(
            """SELECT ocr_payload_json FROM ocr_results
               WHERE file_hash=? AND engine_fingerprint=? ORDER BY page_index""",
            (file_hash, engine_fingerprint),
        ).fetchall()
        return CachedOCR(job[0], tuple(_page_from_json(row[0]) for row in rows), job[1], job[2])

    def store_success(self, source: SourceFile, engine_fingerprint: str, pages: tuple[OCRPage, ...]) -> None:
        self._store(source, engine_fingerprint, "OCR_SUCCEEDED", pages, None, None)

    def store_failure(
        self,
        source: SourceFile,
        engine_fingerprint: str,
        error_code: str,
        error_message: str,
    ) -> None:
        self._store(source, engine_fingerprint, "OCR_FAILED", (), error_code, error_message)

    def _store(
        self,
        source: SourceFile,
        engine_fingerprint: str,
        status: str,
        pages: tuple[OCRPage, ...],
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        processed_at = datetime.now(UTC).isoformat()
        with self.connection:
            self.connection.execute(
                """INSERT INTO files VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_hash) DO UPDATE SET
                   absolute_path=excluded.absolute_path, file_size=excluded.file_size,
                   modified_ns=excluded.modified_ns, extension=excluded.extension,
                   processed_at=excluded.processed_at""",
                (
                    source.file_hash,
                    str(source.path),
                    source.file_size,
                    source.modified_ns,
                    source.extension,
                    processed_at,
                ),
            )
            self.connection.execute(
                "DELETE FROM ocr_results WHERE file_hash=? AND engine_fingerprint=?",
                (source.file_hash, engine_fingerprint),
            )
            self.connection.execute(
                """INSERT INTO ocr_jobs VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(file_hash, engine_fingerprint) DO UPDATE SET
                   status=excluded.status, page_count=excluded.page_count,
                   error_code=excluded.error_code, error_message=excluded.error_message,
                   processed_at=excluded.processed_at""",
                (
                    source.file_hash,
                    engine_fingerprint,
                    status,
                    len(pages),
                    error_code,
                    error_message,
                    processed_at,
                ),
            )
            self.connection.executemany(
                "INSERT INTO ocr_results VALUES (?, ?, ?, ?)",
                ((source.file_hash, engine_fingerprint, page.page_index, _page_to_json(page)) for page in pages),
            )
