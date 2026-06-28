"""
Structured JSON logging with optional async MongoDB storage.

Architecture:
  ┌──────────────┐    queue.Queue()    ┌──────────────┐    bulk_write    ┌─────────┐
  │ recommendation │ ────► (batch) ───► │ LogWorkerThread│ ────────────► │ MongoDB │
  │ engine / query │                   │ (flush: 5s)  │                 │  logs   │
  │ etc.           │                   └──────────────┘                 └─────────┘
  └──────────────┘

Usage:
  from app.logging import logger  # drop-in replacement for logging.getLogger()
  logger.info("query handled", extra={"event": "query.executed", "duration_ms": 1200})
"""

import json
import logging
import os
import queue
import threading
import time
import traceback
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Dict, Optional

from app.config import settings

# ── JSON Formatter ──────────────────────────────────────────────────────────


class JSONFormatter(logging.Formatter):
    """Formats log records as newline-delimited JSON."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Merge extra fields passed via extra={}
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            entry.update(record.extra_fields)

        # Include exception info if present
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = "".join(traceback.format_exception(*record.exc_info))

        # Include process/thread info for worker context
        entry["pid"] = os.getpid()

        return json.dumps(entry, default=str)


# ── Custom Logger ───────────────────────────────────────────────────────────


class StructuredLogger(logging.Logger):
    """Drop-in replacement that sets the JSON formatter automatically."""

    def _log(self, level, msg, args, exc_info=None, extra=None, **kwargs):
        # Capture extra_fields so JSONFormatter can merge them
        if extra and isinstance(extra, dict):
            extra.setdefault("extra_fields", extra)
        super()._log(level, msg, args, exc_info, extra, **kwargs)


# ── Async MongoDB Writer ────────────────────────────────────────────────────


_log_queue: queue.Queue = queue.Queue(maxsize=5000)
_log_worker: Optional["LogWorker"] = None


class LogWorker:
    """Background thread that drains log entries and bulk-writes to MongoDB."""

    def __init__(
        self, mongo_uri: str, db_name: str = "pageturner", collection: str = "logs"
    ):
        self.mongo_uri = mongo_uri
        self.db_name = db_name
        self.collection = collection
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._client = None

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._drain()

    def _get_client(self):
        if self._client is None:
            from pymongo import MongoClient

            self._client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=3000,
                tlsAllowInvalidCertificates=True,
            )
        return self._client

    def _run(self):
        batch: list[dict] = []
        last_flush = time.monotonic()
        while not self._stop.is_set():
            try:
                entry = _log_queue.get(timeout=1)
                batch.append(entry)
            except queue.Empty:
                pass

            # Flush every 5 seconds or 100 entries
            now = time.monotonic()
            if batch and (len(batch) >= 100 or now - last_flush >= 5):
                self._write(batch)
                batch.clear()
                last_flush = now

        # Final flush on shutdown
        if batch:
            self._write(batch)

    def _write(self, batch: list[dict]):
        try:
            client = self._get_client()
            client[self.db_name][self.collection].insert_many(batch, ordered=False)
        except Exception:
            pass  # Logging must never crash the app

    def _drain(self):
        """Flush remaining queue without blocking shutdown."""
        batch = []
        while not _log_queue.empty():
            try:
                batch.append(_log_queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._write(batch)


# ── Queue handler (non-blocking) ────────────────────────────────────────────


class MongoQueueHandler(logging.Handler):
    """Synchronous enqueue — the hot path never waits."""

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.setFormatter(JSONFormatter())

    def emit(self, record: logging.LogRecord):
        try:
            entry = json.loads(self.format(record))
            # Ensure timestamp is a string for MongoDB
            _log_queue.put_nowait(entry)
        except Exception:
            pass  # Never crash the app from logging


# ── Decorator ───────────────────────────────────────────────────────────────


def log_entry_exit(logger_override: Optional[logging.Logger] = None):
    """
    Decorator that auto-logs function entry/exit with duration.

    Usage:
        @log_entry_exit()
        def generate_recommendations(db, user_uuid, raw_query, session_id):
            ...

        @log_entry_exit(my_logger)
        def some_other_function(db, ...):
            ...
    """

    def decorator(func):
        nonlocal logger_override
        _logger = logger_override or logging.getLogger(func.__module__)

        @wraps(func)
        def wrapper(*args, **kwargs):
            module = func.__module__
            name = func.__qualname__
            event_base = f"{module}.{name}"
            _logger.info(
                f"{name} started",
                extra={"event": f"{event_base}.entry"},
            )
            t0 = time.monotonic()
            try:
                result = func(*args, **kwargs)
                duration = round((time.monotonic() - t0) * 1000, 1)
                _logger.info(
                    f"{name} completed",
                    extra={"event": f"{event_base}.exit", "duration_ms": duration},
                )
                return result
            except Exception as e:
                duration = round((time.monotonic() - t0) * 1000, 1)
                _logger.error(
                    f"{name} failed: {e}",
                    extra={"event": f"{event_base}.error", "duration_ms": duration},
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


# ── Bootstrap ───────────────────────────────────────────────────────────────


def setup_logging():
    """
    Call once at app startup (app/main.py).
    Replaces the root logger's handler with JSON formatting
    and starts the async MongoDB writer if MONGO_URI is configured.
    """
    # Prevent duplicate handlers on reload
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    # JSON stdout handler
    stdout_handler = logging.StreamHandler()
    stdout_handler.setFormatter(JSONFormatter())
    stdout_handler.setLevel(logging.INFO)
    root.addHandler(stdout_handler)
    root.setLevel(logging.INFO)

    # MongoDB handler
    if settings.MONGO_URI:
        mongo_handler = MongoQueueHandler()
        mongo_handler.setLevel(logging.INFO)
        root.addHandler(mongo_handler)

        global _log_worker
        _log_worker = LogWorker(
            mongo_uri=settings.MONGO_URI,
            db_name="pageturner",
            collection="logs",
        )
        _log_worker.start()

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return _log_worker
