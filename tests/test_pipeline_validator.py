"""Tests for pure pipeline validation."""

from pathlib import Path

import pytest

from src.analyzer.models import AnalysisConfig, AnalyzerResult
from src.clipper.models import ClipConfiguration, ClipResult
from src.downloader.models import DownloadConfig, DownloadResult, VideoMetadata
from src.pipeline.exceptions import InvalidPipelineRequestError
from src.pipeline.models import PipelineRequest, PipelineResult
from src.pipeline.validator import validate_pipeline_request, validate_pipeline_result
from src.transcript.models import LanguageInfo, TranscriptConfig, TranscriptResult


def _request(source_url: str = "https://www.youtube.com/watch?v=abc123") -> PipelineRequest:
    """Build a structurally valid pipeline request."""
    return PipelineRequest(source_url, DownloadConfig(Path("downloads")), TranscriptConfig("small"), AnalysisConfig(), ClipConfiguration(Path("output")))


def test_validate_pipeline_request_accepts_valid_configuration() -> None:
    """Valid stage configuration returns the original immutable request."""
    request = _request()
    assert validate_pipeline_request(request) is request


@pytest.mark.parametrize("pipeline_request", ["bad", _request("")])
def test_validate_pipeline_request_rejects_invalid_structure(pipeline_request: object) -> None:
    """Invalid pipeline boundaries expose only pipeline exceptions."""
    with pytest.raises(InvalidPipelineRequestError):
        validate_pipeline_request(pipeline_request)  # type: ignore[arg-type]


def test_validate_pipeline_result_rejects_invalid_duration() -> None:
    """Final results require non-negative non-boolean elapsed time."""
    metadata = VideoMetadata("id", "title", 1, None, "url", None)
    download = DownloadResult(Path("source.mp4"), metadata, False)
    transcript = TranscriptResult(Path("source.mp4"), "Text", (), LanguageInfo("en", "English", True), "fake", 0)
    analysis = AnalyzerResult(Path("source.mp4"), (), (), "fake", 0)
    result = PipelineResult(download, transcript, analysis, ClipResult(Path("source.mp4"), (), 0), -1)
    with pytest.raises(InvalidPipelineRequestError):
        validate_pipeline_result(result)

def test_validator_rejects_invalid_stage_configurations_and_identifiers() -> None:
    request = _request()
    invalid_config = type(request)(request.source_url, "bad", request.transcript_config, request.analysis_config, request.clip_configuration)  # type: ignore[arg-type]
    with pytest.raises(InvalidPipelineRequestError): validate_pipeline_request(invalid_config)
    invalid_name = type(request)(request.source_url, request.download_config, request.transcript_config, request.analysis_config, request.clip_configuration, transcription_backend_name="Bad Name")
    with pytest.raises(InvalidPipelineRequestError): validate_pipeline_request(invalid_name)
