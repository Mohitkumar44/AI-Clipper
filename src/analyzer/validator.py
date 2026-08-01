"""Pure validation utilities for provider-independent analyzer contracts."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.transcript.models import TranscriptResult

from .exceptions import InvalidAnalysisRequestError, InvalidAnalysisResultError
from .models import AnalysisConfig, AnalyzerRequest, AnalyzerResult, ClipCandidate, ViralMoment


LOGGER = logging.getLogger(__name__)
LANGUAGE_CODE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[a-z]{2,4})?$")
MAX_CUSTOM_INSTRUCTION_LENGTH = 4_000
MINIMUM_SCORE = 0.0
MAXIMUM_SCORE = 100.0


def validate_analyzer_request(request: AnalyzerRequest) -> AnalyzerRequest:
    """Validate a complete analyzer request without analyzing transcript text.

    Args:
        request: Request containing a local source path, transcript, and config.

    Returns:
        The original validated request.

    Raises:
        InvalidAnalysisRequestError: If the request violates input invariants.
    """
    if not isinstance(request, AnalyzerRequest):
        raise InvalidAnalysisRequestError("request must be an AnalyzerRequest instance.")
    _validate_source_path(request.source_path)
    validate_analysis_config(request.config)
    _validate_transcript_availability(request.transcript)
    if request.analyzer_name is not None and not _is_identifier(request.analyzer_name):
        raise InvalidAnalysisRequestError("analyzer_name must be a lowercase identifier.")
    LOGGER.debug("analyzer_request_validated", extra={"event": "analyzer_request_validated"})
    return request


def validate_analysis_config(config: AnalysisConfig) -> AnalysisConfig:
    """Validate provider-neutral analysis limits and optional instructions.

    Args:
        config: Immutable analysis configuration.

    Returns:
        The original validated configuration.

    Raises:
        InvalidAnalysisRequestError: If a configuration value is invalid.
    """
    if not isinstance(config, AnalysisConfig):
        raise InvalidAnalysisRequestError("config must be an AnalysisConfig instance.")
    if not _is_positive_integer(config.maximum_candidates):
        raise InvalidAnalysisRequestError("maximum_candidates must be positive.")
    if not _is_positive_number(config.minimum_clip_duration_seconds):
        raise InvalidAnalysisRequestError("minimum_clip_duration_seconds must be positive.")
    if not _is_positive_number(config.maximum_clip_duration_seconds):
        raise InvalidAnalysisRequestError("maximum_clip_duration_seconds must be positive.")
    if config.maximum_clip_duration_seconds < config.minimum_clip_duration_seconds:
        raise InvalidAnalysisRequestError("maximum clip duration must not be less than minimum duration.")
    _validate_language_code(config.target_language_code)
    if config.custom_instructions is not None:
        if not isinstance(config.custom_instructions, str):
            raise InvalidAnalysisRequestError("custom_instructions must be a string or None.")
        if len(config.custom_instructions) > MAX_CUSTOM_INSTRUCTION_LENGTH:
            raise InvalidAnalysisRequestError("custom_instructions exceeds the configured length limit.")
    if not isinstance(config.include_transcript_excerpt, bool):
        raise InvalidAnalysisRequestError("include_transcript_excerpt must be a boolean.")
    return config


def validate_analyzer_result(
    result: AnalyzerResult,
    config: AnalysisConfig | None = None,
) -> AnalyzerResult:
    """Validate complete clip-analysis output and candidate ranking.

    Args:
        result: Provider-independent analysis output to validate.
        config: Optional request configuration that supplied result limits.

    Returns:
        The original validated result.

    Raises:
        InvalidAnalysisResultError: If result data violates output invariants.
    """
    if not isinstance(result, AnalyzerResult):
        raise InvalidAnalysisResultError("result must be an AnalyzerResult instance.")
    selected_config = config or AnalysisConfig()
    try:
        validate_analysis_config(selected_config)
        _validate_source_path(result.source_path)
    except InvalidAnalysisRequestError as error:
        raise InvalidAnalysisResultError("analysis result contains invalid shared data.") from error

    if not _is_identifier(result.analyzer_name):
        raise InvalidAnalysisResultError("analyzer_name must be a lowercase identifier.")
    if not _is_non_negative_number(result.processing_time_seconds):
        raise InvalidAnalysisResultError("processing_time_seconds must be non-negative.")
    if len(result.candidates) > selected_config.maximum_candidates:
        raise InvalidAnalysisResultError("result exceeds the configured maximum candidate count.")

    candidate_ids: set[str] = set()
    previous_score: float | None = None
    for candidate in result.candidates:
        validate_clip_candidate(candidate, selected_config)
        if candidate.candidate_id in candidate_ids:
            raise InvalidAnalysisResultError("candidate IDs must be unique.")
        if previous_score is not None and candidate.score > previous_score:
            raise InvalidAnalysisResultError("candidates must be ordered by descending score.")
        candidate_ids.add(candidate.candidate_id)
        previous_score = candidate.score

    moment_ids: set[str] = set()
    for moment in result.viral_moments:
        validate_viral_moment(moment)
        if moment.moment_id in moment_ids:
            raise InvalidAnalysisResultError("viral moment IDs must be unique.")
        moment_ids.add(moment.moment_id)

    LOGGER.debug("analyzer_result_validated", extra={"event": "analyzer_result_validated"})
    return result


def validate_clip_candidate(candidate: ClipCandidate, config: AnalysisConfig) -> ClipCandidate:
    """Validate one proposed clip range against configured duration limits.

    Args:
        candidate: Candidate clip returned by an analyzer implementation.
        config: Validated analysis configuration defining duration limits.

    Returns:
        The original validated candidate.

    Raises:
        InvalidAnalysisResultError: If the candidate is malformed or out of range.
    """
    if not isinstance(candidate, ClipCandidate):
        raise InvalidAnalysisResultError("candidate must be a ClipCandidate instance.")
    if not _is_identifier(candidate.candidate_id):
        raise InvalidAnalysisResultError("candidate_id must be a lowercase identifier.")
    _validate_timestamp_range(candidate.start_seconds, candidate.end_seconds)
    duration = candidate.end_seconds - candidate.start_seconds
    if duration < config.minimum_clip_duration_seconds or duration > config.maximum_clip_duration_seconds:
        raise InvalidAnalysisResultError("candidate duration is outside configured limits.")
    _validate_score(candidate.score)
    if not _is_non_blank_string(candidate.reason):
        raise InvalidAnalysisResultError("candidate reason must not be blank.")
    return candidate


def validate_viral_moment(moment: ViralMoment) -> ViralMoment:
    """Validate one classified viral moment.

    Args:
        moment: Viral moment returned by an analyzer implementation.

    Returns:
        The original validated viral moment.

    Raises:
        InvalidAnalysisResultError: If the moment is malformed.
    """
    if not isinstance(moment, ViralMoment):
        raise InvalidAnalysisResultError("moment must be a ViralMoment instance.")
    if not _is_identifier(moment.moment_id):
        raise InvalidAnalysisResultError("moment_id must be a lowercase identifier.")
    _validate_timestamp_range(moment.start_seconds, moment.end_seconds)
    _validate_score(moment.score)
    if not _is_non_blank_string(moment.explanation):
        raise InvalidAnalysisResultError("moment explanation must not be blank.")
    return moment


def _validate_source_path(source_path: Path) -> None:
    """Ensure a source path references an existing regular file."""
    if not isinstance(source_path, Path):
        raise InvalidAnalysisRequestError("source_path must be a pathlib.Path instance.")
    try:
        is_file = source_path.is_file()
    except OSError as error:
        raise InvalidAnalysisRequestError("source_path could not be accessed.") from error
    if not is_file:
        raise InvalidAnalysisRequestError("source_path must reference an existing file.")


def _validate_transcript_availability(transcript: TranscriptResult) -> None:
    """Ensure a completed transcript has text or timestamped segments to analyze."""
    if not isinstance(transcript, TranscriptResult):
        raise InvalidAnalysisRequestError("transcript must be a TranscriptResult instance.")
    if not isinstance(transcript.full_text, str) or not isinstance(transcript.segments, tuple):
        raise InvalidAnalysisRequestError("transcript must contain valid text and segment data.")
    if not transcript.segments and not transcript.full_text.strip():
        raise InvalidAnalysisRequestError("transcript must contain text or segments.")


def _validate_language_code(language_code: str | None) -> None:
    """Validate an optional ISO-style target language code."""
    if language_code is not None and (
        not isinstance(language_code, str) or not LANGUAGE_CODE_PATTERN.fullmatch(language_code)
    ):
        raise InvalidAnalysisRequestError("target_language_code has an invalid format.")


def _validate_timestamp_range(start_seconds: float, end_seconds: float) -> None:
    """Validate a non-negative, non-empty timestamp range."""
    if not _is_non_negative_number(start_seconds) or not _is_non_negative_number(end_seconds):
        raise InvalidAnalysisResultError("timestamps must be non-negative numbers.")
    if end_seconds <= start_seconds:
        raise InvalidAnalysisResultError("end timestamp must be greater than start timestamp.")


def _validate_score(score: float) -> None:
    """Validate a normalized inclusive 0-to-100 ranking score."""
    if not _is_non_negative_number(score) or score < MINIMUM_SCORE or score > MAXIMUM_SCORE:
        raise InvalidAnalysisResultError("score must be between 0 and 100.")


def _is_identifier(value: object) -> bool:
    """Return whether a value is a non-blank portable identifier."""
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z][a-z0-9_-]*", value))


def _is_non_blank_string(value: object) -> bool:
    """Return whether a value is a non-blank string."""
    return isinstance(value, str) and bool(value.strip())


def _is_positive_number(value: object) -> bool:
    """Return whether a value is numeric, positive, and not boolean."""
    return _is_non_negative_number(value) and value > 0


def _is_positive_integer(value: object) -> bool:
    """Return whether a value is a positive integer and not boolean."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_number(value: object) -> bool:
    """Return whether a value is numeric, non-negative, and not boolean."""
    return isinstance(value, int | float) and not isinstance(value, bool) and value >= 0
