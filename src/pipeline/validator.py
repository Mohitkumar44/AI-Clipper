"""Pure validation utilities for pipeline orchestration contracts."""

from __future__ import annotations

from src.analyzer.models import AnalysisConfig
from src.clipper.models import ClipConfiguration
from src.downloader.models import DownloadConfig
from src.transcript.models import TranscriptConfig

from .exceptions import InvalidPipelineRequestError
from .models import PipelineRequest, PipelineResult


def validate_pipeline_request(request: PipelineRequest) -> PipelineRequest:
    """Validate pipeline request structure without executing any workflow stage.

    Args:
        request: Immutable pipeline request to validate.

    Returns:
        The original validated request.

    Raises:
        InvalidPipelineRequestError: If required request values are missing.
    """
    if not isinstance(request, PipelineRequest):
        raise InvalidPipelineRequestError("request must be a PipelineRequest instance.")
    if not isinstance(request.source_url, str) or not request.source_url.strip():
        raise InvalidPipelineRequestError("source_url must not be blank.")
    if not isinstance(request.download_config, DownloadConfig):
        raise InvalidPipelineRequestError("download_config must be a DownloadConfig instance.")
    if not isinstance(request.transcript_config, TranscriptConfig):
        raise InvalidPipelineRequestError("transcript_config must be a TranscriptConfig instance.")
    if not isinstance(request.analysis_config, AnalysisConfig):
        raise InvalidPipelineRequestError("analysis_config must be an AnalysisConfig instance.")
    if not isinstance(request.clip_configuration, ClipConfiguration):
        raise InvalidPipelineRequestError("clip_configuration must be a ClipConfiguration instance.")
    if request.transcription_backend_name is not None and not _is_identifier(request.transcription_backend_name):
        raise InvalidPipelineRequestError("transcription_backend_name is invalid.")
    if request.analyzer_name is not None and not _is_identifier(request.analyzer_name):
        raise InvalidPipelineRequestError("analyzer_name is invalid.")
    return request


def validate_pipeline_result(result: PipelineResult) -> PipelineResult:
    """Validate the immutable result assembled after all stages succeed.

    Args:
        result: Pipeline result to validate.

    Returns:
        The original validated result.

    Raises:
        InvalidPipelineRequestError: If the assembled result is malformed.
    """
    if not isinstance(result, PipelineResult):
        raise InvalidPipelineRequestError("result must be a PipelineResult instance.")
    if (
        not isinstance(result.processing_time_seconds, int | float)
        or isinstance(result.processing_time_seconds, bool)
        or result.processing_time_seconds < 0
    ):
        raise InvalidPipelineRequestError("processing_time_seconds must be non-negative.")
    return result


def _is_identifier(value: object) -> bool:
    """Return whether a value is a lowercase portable identifier."""
    return isinstance(value, str) and value.replace("_", "").replace("-", "").isalnum() and value[:1].islower()
