"""Pure validation utilities for transcript-domain data contracts."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .exceptions import (
    InvalidTranscriptRequestError,
    MediaFileNotFoundError,
    MediaFormatNotSupportedError,
    TranscriptValidationError,
    UnsupportedLanguageError,
)
from .models import (
    LanguageInfo,
    TranscriptConfig,
    TranscriptRequest,
    TranscriptResult,
    TranscriptSegment,
    TranscriptTask,
)


LOGGER = logging.getLogger(__name__)
LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?$")
BACKEND_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
SUPPORTED_MEDIA_SUFFIXES = frozenset(
    {".aac", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm"}
)


def validate_transcript_request(request: TranscriptRequest) -> TranscriptRequest:
    """Validate a transcript request without opening its media file.

    Raises:
        InvalidTranscriptRequestError: If the request or task is invalid.
        TranscriptError: If a nested request value is invalid.
    """
    if not isinstance(request, TranscriptRequest):
        raise InvalidTranscriptRequestError("request must be a TranscriptRequest instance.")

    validate_media_path(request.media_path)
    validate_transcript_config(request.config)
    validate_language_code(request.language_code)
    validate_backend_name(request.backend_name)
    if not isinstance(request.task, TranscriptTask):
        raise InvalidTranscriptRequestError("task must be a TranscriptTask value.")

    LOGGER.debug("transcript_request_validated", extra={"event": "transcript_request_validated"})
    return request


def validate_media_path(media_path: Path) -> Path:
    """Validate a supported existing local media-file path without reading it.

    Raises:
        InvalidTranscriptRequestError: If the path is not a ``Path`` instance.
        MediaFileNotFoundError: If the path does not reference a regular file.
        MediaFormatNotSupportedError: If the filename suffix is unsupported.
    """
    if not isinstance(media_path, Path):
        raise InvalidTranscriptRequestError("media_path must be a pathlib.Path instance.")
    if media_path.suffix.lower() not in SUPPORTED_MEDIA_SUFFIXES:
        raise MediaFormatNotSupportedError("The media file has an unsupported format.")

    try:
        is_file = media_path.is_file()
    except OSError as error:
        raise MediaFileNotFoundError("The media file could not be accessed.") from error
    if not is_file:
        raise MediaFileNotFoundError("The media file does not exist.")
    return media_path


def validate_language_code(language_code: str | None) -> str | None:
    """Validate an optional ISO-style language code without backend lookups.

    Raises:
        UnsupportedLanguageError: If a language code has an invalid structure.
    """
    if language_code is None:
        return None
    if not isinstance(language_code, str) or not LANGUAGE_CODE_PATTERN.fullmatch(language_code):
        raise UnsupportedLanguageError("language_code must use a supported ISO-style code.")
    return language_code


def validate_transcript_config(config: TranscriptConfig) -> TranscriptConfig:
    """Validate immutable transcription settings without loading a model.

    Raises:
        InvalidTranscriptRequestError: If settings are incomplete or malformed.
    """
    if not isinstance(config, TranscriptConfig):
        raise InvalidTranscriptRequestError("config must be a TranscriptConfig instance.")
    if not _is_non_blank_string(config.model_name):
        raise InvalidTranscriptRequestError("model_name must not be blank.")
    if not _is_non_blank_string(config.device):
        raise InvalidTranscriptRequestError("device must not be blank.")
    if not _is_non_blank_string(config.compute_type):
        raise InvalidTranscriptRequestError("compute_type must not be blank.")
    if not isinstance(config.word_timestamps, bool):
        raise InvalidTranscriptRequestError("word_timestamps must be a boolean.")
    if config.initial_prompt is not None and not isinstance(config.initial_prompt, str):
        raise InvalidTranscriptRequestError("initial_prompt must be a string or None.")
    return config


def validate_backend_name(backend_name: str | None) -> str | None:
    """Validate an optional portable backend identifier.

    Raises:
        InvalidTranscriptRequestError: If the backend identifier is malformed.
    """
    if backend_name is None:
        return None
    if not isinstance(backend_name, str) or not BACKEND_NAME_PATTERN.fullmatch(backend_name):
        raise InvalidTranscriptRequestError("backend_name must be a lowercase identifier.")
    return backend_name


def validate_transcript_result(result: TranscriptResult) -> TranscriptResult:
    """Validate timestamp ordering and required result data from a backend.

    Raises:
        TranscriptValidationError: If result data violates transcript invariants.
    """
    if not isinstance(result, TranscriptResult):
        raise TranscriptValidationError("result must be a TranscriptResult instance.")
    if not isinstance(result.source_path, Path):
        raise TranscriptValidationError("source_path must be a pathlib.Path instance.")
    if not _is_non_blank_string(result.backend_name):
        raise TranscriptValidationError("backend_name must not be blank.")
    if not _is_non_negative_number(result.processing_time_seconds):
        raise TranscriptValidationError("processing_time_seconds must be non-negative.")
    if result.duration_seconds is not None and not _is_non_negative_number(result.duration_seconds):
        raise TranscriptValidationError("duration_seconds must be non-negative or None.")

    _validate_language_info(result.language)
    _validate_segments(result.segments)
    LOGGER.debug("transcript_result_validated", extra={"event": "transcript_result_validated"})
    return result


def _validate_language_info(language: LanguageInfo) -> None:
    """Validate language information returned by a transcription backend."""
    if not isinstance(language, LanguageInfo):
        raise TranscriptValidationError("language must be a LanguageInfo instance.")
    try:
        validate_language_code(language.code)
    except UnsupportedLanguageError as error:
        raise TranscriptValidationError("language.code is invalid.") from error
    if not _is_non_blank_string(language.name):
        raise TranscriptValidationError("language.name must not be blank.")


def _validate_segments(segments: tuple[TranscriptSegment, ...]) -> None:
    """Validate ordered, non-overlapping, timestamped transcript segments."""
    previous_end = 0.0
    previous_id = -1
    for segment in segments:
        if not isinstance(segment, TranscriptSegment):
            raise TranscriptValidationError("segments must contain TranscriptSegment values.")
        if segment.segment_id <= previous_id:
            raise TranscriptValidationError("segment IDs must be strictly increasing.")
        if not _is_non_negative_number(segment.start_seconds):
            raise TranscriptValidationError("segment start time must be non-negative.")
        if not _is_non_negative_number(segment.end_seconds):
            raise TranscriptValidationError("segment end time must be non-negative.")
        if segment.end_seconds < segment.start_seconds:
            raise TranscriptValidationError("segment end time must not precede start time.")
        if segment.start_seconds < previous_end:
            raise TranscriptValidationError("segments must not overlap.")
        if not _is_non_blank_string(segment.text):
            raise TranscriptValidationError("segment text must not be blank.")
        previous_id = segment.segment_id
        previous_end = float(segment.end_seconds)


def _is_non_blank_string(value: object) -> bool:
    """Return whether a value is a non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def _is_non_negative_number(value: object) -> bool:
    """Return whether a value is numeric, non-negative, and not boolean."""
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0
