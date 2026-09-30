"""
Project Lucca — Unified Process Logging & Crash Forensics
Captures all process output, logging records, and uncaught exceptions to persistent files.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import traceback
from typing import TextIO

from lucca.core.config import get_config

logger = logging.getLogger("lucca.logging_setup")


class _TeeStream:
    """Mirrors stream writes to both the original console stream and a persistent log file."""

    def __init__(self, original_stream: TextIO | None, log_file: TextIO) -> None:
        self._orig = original_stream
        self._log = log_file

    def write(self, s: str) -> int:
        if self._orig:
            try:
                self._orig.write(s)
            except Exception as exc:
                logger.debug("tee_orig_write_failed: %s", exc)
        try:
            self._log.write(s)
            self._log.flush()
        except Exception as exc:
            logger.debug("tee_log_write_failed: %s", exc)
        return len(s)

    def flush(self) -> None:
        if self._orig:
            try:
                self._orig.flush()
            except Exception as exc:
                logger.debug("tee_orig_flush_failed: %s", exc)
        try:
            self._log.flush()
        except Exception as exc:
            logger.debug("tee_log_flush_failed: %s", exc)

    def isatty(self) -> bool:
        if self._orig and hasattr(self._orig, "isatty"):
            try:
                return self._orig.isatty()
            except Exception as exc:
                logger.debug("tee_isatty_failed: %s", exc)
                return False
        return False

    def __getattr__(self, name: str) -> object:
        if self._orig is not None and hasattr(self._orig, name):
            return getattr(self._orig, name)
        return getattr(self._log, name)


def setup_process_logging(process_name: str) -> Path:
    """Configures persistent rotating logging and crash hooks for a Lucca process."""
    try:
        config = get_config()
        logs_dir = Path(config.home_dir) / "logs"
    except Exception as exc:
        logger.debug("resolve_home_dir_failed_using_default: %s", exc)
        logs_dir = Path(r"C:\ProjectLucca\logs")
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = logs_dir / f"{process_name}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Check if this process handler is already installed
    has_file_handler = any(
        isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str(log_file_path.resolve())
        for h in root_logger.handlers
    )
    if not has_file_handler:
        file_handler = RotatingFileHandler(
            str(log_file_path),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # Persistent raw log stream for stdout/stderr capturing
    try:
        raw_log = open(log_file_path, "a", encoding="utf-8", errors="replace")
        if sys.stdout is not None:
            sys.stdout = _TeeStream(sys.stdout, raw_log)
        if sys.stderr is not None:
            sys.stderr = _TeeStream(sys.stderr, raw_log)
    except Exception as exc:
        logger.debug("tee_stream_init_failed: %s", exc)

    # Install global uncaught exception hook
    def _crash_hook(exc_type: type[BaseException], exc_val: BaseException, tb: object) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_val, tb)
            return

        err_msg = "".join(traceback.format_exception(exc_type, exc_val, tb))
        timestamp = logging.Formatter().formatTime(logging.LogRecord("", 0, "", 0, "", (), None))
        crash_header = f"\n{'='*70}\n[CRASH] Unhandled exception in process '{process_name}' at {timestamp}:\n{err_msg}{'='*70}\n"

        root_logger.critical("Unhandled exception in process %s:\n%s", process_name, err_msg)
        try:
            with open(log_file_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(crash_header)
                f.flush()
        except Exception as exc:
            logger.debug("write_crash_log_failed: %s", exc)

        if sys.__stderr__:
            try:
                sys.__stderr__.write(crash_header)
                sys.__stderr__.flush()
            except Exception as exc:
                logger.debug("write_crash_stderr_failed: %s", exc)

    sys.excepthook = _crash_hook

    root_logger.info("Process '%s' logging initialized at %s", process_name, log_file_path)
    return log_file_path
