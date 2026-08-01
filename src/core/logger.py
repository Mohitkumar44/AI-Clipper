"""Application-wide logging configuration and logger retrieval."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


DEFAULT_LOG_FILENAME = "ai_clipper.log"
DEFAULT_MAX_LOG_BYTES = 5 * 1_024 * 1_024
DEFAULT_BACKUP_COUNT = 5
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(
    log_directory: Path,
    *,
    level: int = logging.INFO,
    log_filename: str = DEFAULT_LOG_FILENAME,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> None:
    """Configure console and rotating-file handlers for the root logger.

    The setup is idempotent for a given log file: repeated calls replace only
    handlers installed by this function, preventing duplicate log messages.

    Args:
        log_directory: Directory where the log file should be stored.
        level: Minimum severity written by configured handlers.
        log_filename: Filename for the rotating log.
        max_bytes: Maximum size of a single log before rotation.
        backup_count: Number of rotated log files to keep.
    """
    _validate_logging_arguments(log_directory, log_filename, max_bytes, backup_count)
    log_directory.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    log_path = log_directory / log_filename

    for handler in tuple(root_logger.handlers):
        if getattr(handler, "_ai_clipper_handler", False):
            root_logger.removeHandler(handler)
            handler.close()

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    console_handler._ai_clipper_handler = True  # type: ignore[attr-defined]

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    file_handler._ai_clipper_handler = True  # type: ignore[attr-defined]

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger after validating its stable module identifier."""
    if not name or not name.strip():
        raise ValueError("Logger name must not be blank.")
    return logging.getLogger(name)


def _validate_logging_arguments(
    log_directory: Path,
    log_filename: str,
    max_bytes: int,
    backup_count: int,
) -> None:
    """Validate logger setup inputs before changing logging configuration."""
    if not isinstance(log_directory, Path):
        raise TypeError("log_directory must be a pathlib.Path instance.")
    if not log_filename or Path(log_filename).name != log_filename:
        raise ValueError("log_filename must be a filename without path components.")
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive.")
    if backup_count < 1:
        raise ValueError("backup_count must be positive.")
