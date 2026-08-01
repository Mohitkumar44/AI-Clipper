"""Pure validation utilities for provider-independent clip-rendering contracts."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.core.config import ApplicationConfig

from .exceptions import (
    InvalidClipRequestError,
    InvalidTimestampError,
    OutputWriteError,
    UnsupportedFormatError,
)
from .models import (
    ClipCandidate,
    ClipConfiguration,
    ClipFormat,
    ClipRequest,
    RenderedClip,
)


LOGGER = logging.getLogger(__name__)
CODEC_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
INVALID_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
WINDOWS_RESERVED_NAMES = frozenset(
    {
        "con", "prn", "aux", "nul",
        "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
        "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
    }
)


def validate_clip_request(request: ClipRequest, application_config: ApplicationConfig) -> ClipRequest:
    """Validate a complete clip-rendering request without accessing media.

    Args:
        request: Immutable clip-rendering request to validate.
        application_config: Shared configuration defining the controlled output root.

    Returns:
        The original validated request.

    Raises:
        InvalidClipRequestError: If the request or duplicate candidate IDs are invalid.
        InvalidTimestampError: If a candidate time range is invalid.
        UnsupportedFormatError: If output format configuration is unsupported.
    """
    if not isinstance(request, ClipRequest):
        raise InvalidClipRequestError("request must be a ClipRequest instance.")
    validate_clip_configuration(request.configuration, application_config)
    if not isinstance(request.candidates, tuple):
        raise InvalidClipRequestError("candidates must be an immutable tuple.")

    candidate_ids: set[str] = set()
    for candidate in request.candidates:
        validate_clip_candidate(candidate)
        if candidate.candidate_id in candidate_ids:
            raise InvalidClipRequestError("candidate IDs must be unique.")
        candidate_ids.add(candidate.candidate_id)

    LOGGER.debug("clip_request_validated", extra={"event": "clip_request_validated"})
    return request


def validate_clip_candidate(candidate: ClipCandidate) -> ClipCandidate:
    """Validate one selected timestamp range ready for rendering.

    Args:
        candidate: Candidate clip range to validate.

    Returns:
        The original validated candidate.

    Raises:
        InvalidClipRequestError: If the candidate identifier or metadata is invalid.
        InvalidTimestampError: If the candidate time range is invalid.
    """
    if not isinstance(candidate, ClipCandidate):
        raise InvalidClipRequestError("candidate must be a ClipCandidate instance.")
    if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id.strip():
        raise InvalidClipRequestError("candidate_id must not be blank.")
    validate_timestamp_range(candidate.start_seconds, candidate.end_seconds)
    if not _is_score(candidate.score):
        raise InvalidClipRequestError("candidate score must be between 0 and 100.")
    if not isinstance(candidate.reason, str) or not candidate.reason.strip():
        raise InvalidClipRequestError("candidate reason must not be blank.")
    return candidate


def validate_clip_configuration(
    configuration: ClipConfiguration,
    application_config: ApplicationConfig,
) -> ClipConfiguration:
    """Validate output settings against the application-controlled output root.

    Args:
        configuration: Immutable output and codec settings.
        application_config: Shared configuration defining the output root.

    Returns:
        The original validated configuration.

    Raises:
        InvalidClipRequestError: If output paths, codecs, or overwrite policy are invalid.
        UnsupportedFormatError: If the selected output format is unsupported.
    """
    if not isinstance(configuration, ClipConfiguration):
        raise InvalidClipRequestError("configuration must be a ClipConfiguration instance.")
    if not isinstance(application_config, ApplicationConfig):
        raise InvalidClipRequestError("application_config must be an ApplicationConfig instance.")
    if not isinstance(configuration.output_format, ClipFormat):
        raise UnsupportedFormatError("output_format must be a supported ClipFormat value.")
    _validate_controlled_directory(configuration.output_directory, application_config.output_directory)
    _validate_codec(configuration.video_codec, "video_codec")
    _validate_codec(configuration.audio_codec, "audio_codec")
    if not isinstance(configuration.overwrite, bool):
        raise InvalidClipRequestError("overwrite must be a boolean.")
    if not isinstance(configuration.include_audio, bool):
        raise InvalidClipRequestError("include_audio must be a boolean.")
    return configuration


def validate_output_path(
    output_path: Path,
    configuration: ClipConfiguration,
    application_config: ApplicationConfig,
) -> Path:
    """Validate a safe rendered output path under the configured output directory.

    Args:
        output_path: Intended local output media path.
        configuration: Validated output settings including format and directory.
        application_config: Shared configuration defining the output root.

    Returns:
        The original validated output path.

    Raises:
        OutputWriteError: If the path escapes its controlled output directory.
        UnsupportedFormatError: If its filename extension mismatches configured format.
    """
    validate_clip_configuration(configuration, application_config)
    if not isinstance(output_path, Path):
        raise OutputWriteError("output_path must be a pathlib.Path instance.")
    _validate_safe_filename(output_path)

    expected_suffix = f".{configuration.output_format.value}"
    if output_path.suffix.lower() != expected_suffix:
        raise UnsupportedFormatError("output filename extension does not match output_format.")
    try:
        output_path.resolve().relative_to(configuration.output_directory.resolve())
    except (OSError, ValueError) as error:
        raise OutputWriteError("output_path must remain inside output_directory.") from error
    return output_path


def validate_timestamp_range(start_seconds: float, end_seconds: float) -> tuple[float, float]:
    """Validate a non-negative, non-empty source-media timestamp range.

    Args:
        start_seconds: Clip start timestamp.
        end_seconds: Clip end timestamp.

    Returns:
        The original start and end timestamps.

    Raises:
        InvalidTimestampError: If timestamps are non-numeric, negative, or reversed.
    """
    if not _is_non_negative_number(start_seconds) or not _is_non_negative_number(end_seconds):
        raise InvalidTimestampError("timestamps must be non-negative numbers.")
    if end_seconds <= start_seconds:
        raise InvalidTimestampError("end timestamp must be greater than start timestamp.")
    return start_seconds, end_seconds


def validate_rendered_clip(
    rendered_clip: RenderedClip,
    configuration: ClipConfiguration,
    application_config: ApplicationConfig,
) -> RenderedClip:
    """Validate a rendered-clip result for path and timestamp consistency.

    Args:
        rendered_clip: Rendered output model returned by a cutting backend.
        configuration: Configuration used to render the output.
        application_config: Shared configuration defining the output root.

    Returns:
        The original validated rendered-clip model.

    Raises:
        InvalidClipRequestError: If rendered metadata is inconsistent.
        OutputWriteError: If the output path is unsafe.
    """
    if not isinstance(rendered_clip, RenderedClip):
        raise InvalidClipRequestError("rendered_clip must be a RenderedClip instance.")
    if not isinstance(rendered_clip.candidate_id, str) or not rendered_clip.candidate_id.strip():
        raise InvalidClipRequestError("rendered candidate_id must not be blank.")
    validate_timestamp_range(rendered_clip.start_seconds, rendered_clip.end_seconds)
    if not _is_positive_number(rendered_clip.duration_seconds):
        raise InvalidClipRequestError("rendered clip duration must be greater than zero.")
    if rendered_clip.output_format is not configuration.output_format:
        raise UnsupportedFormatError("rendered format does not match configuration.")
    validate_output_path(rendered_clip.output_path, configuration, application_config)
    return rendered_clip


def _validate_controlled_directory(output_directory: Path, application_output_directory: Path) -> None:
    """Ensure an output directory cannot escape the application output root."""
    if not isinstance(output_directory, Path):
        raise InvalidClipRequestError("output_directory must be a pathlib.Path instance.")
    try:
        output_directory.resolve().relative_to(application_output_directory.resolve())
    except (OSError, ValueError) as error:
        raise InvalidClipRequestError("output_directory must be application controlled.") from error


def _validate_codec(codec: str, field_name: str) -> None:
    """Validate a backend codec token without constructing FFmpeg arguments."""
    if not isinstance(codec, str) or not CODEC_PATTERN.fullmatch(codec):
        raise InvalidClipRequestError(f"{field_name} must be a safe codec identifier.")


def _validate_safe_filename(output_path: Path) -> None:
    """Reject path traversal and Windows-unsafe output filenames."""
    filename = output_path.name
    if filename != str(output_path) and output_path.is_absolute() is False and output_path.parent != Path("."):
        raise OutputWriteError("output_path must not contain relative path traversal.")
    if not filename or filename in {".", ".."}:
        raise OutputWriteError("output filename must not be blank.")
    if any(character in INVALID_FILENAME_CHARACTERS for character in filename):
        raise OutputWriteError("output filename contains unsafe characters.")
    if filename.endswith((".", " ")):
        raise OutputWriteError("output filename must not end with a period or space.")
    if filename.split(".", maxsplit=1)[0].lower() in WINDOWS_RESERVED_NAMES:
        raise OutputWriteError("output filename uses a reserved Windows name.")


def _is_score(value: object) -> bool:
    """Return whether a value is a normalized inclusive 0-to-100 score."""
    return _is_non_negative_number(value) and value <= 100


def _is_positive_number(value: object) -> bool:
    """Return whether a value is numeric, positive, and not boolean."""
    return _is_non_negative_number(value) and value > 0


def _is_non_negative_number(value: object) -> bool:
    """Return whether a value is numeric, non-negative, and not boolean."""
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0
