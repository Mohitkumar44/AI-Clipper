"""Tests for immutable pipeline models."""

from pathlib import Path

import pytest

from src.analyzer.models import AnalysisConfig, AnalyzerResult
from src.clipper.models import ClipConfiguration, ClipResult
from src.downloader.models import DownloadConfig, DownloadResult, VideoMetadata
from src.pipeline.models import PipelineProgress, PipelineRequest, PipelineResult, PipelineStage
from src.transcript.models import LanguageInfo, TranscriptConfig, TranscriptResult


def _request() -> PipelineRequest:
    """Build a provider-neutral pipeline request without external resources."""
    return PipelineRequest(
        "https://www.youtube.com/watch?v=abc123",
        DownloadConfig(Path("downloads")),
        TranscriptConfig("small"),
        AnalysisConfig(),
        ClipConfiguration(Path("output")),
    )


def test_pipeline_models_are_immutable() -> None:
    """Workflow configuration is frozen for the full multi-stage run."""
    request = _request()
    progress = PipelineProgress(PipelineStage.DOWNLOADING, 0, 4)
    assert progress.stage is PipelineStage.DOWNLOADING
    with pytest.raises(AttributeError):
        request.source_url = "https://youtube.com/watch?v=other"  # type: ignore[misc]


def test_pipeline_result_retains_all_stage_outputs() -> None:
    """The final model preserves typed results from each completed stage."""
    metadata = VideoMetadata("abc123", "Title", 60, None, "url", None)
    download = DownloadResult(Path("source.mp4"), metadata, False)
    transcript = TranscriptResult(Path("source.mp4"), "Text", (), LanguageInfo("en", "English", True), "fake", 0)
    analysis = AnalyzerResult(Path("source.mp4"), (), (), "fake", 0)
    clips = ClipResult(Path("source.mp4"), (), 0)
    result = PipelineResult(download, transcript, analysis, clips, 1.0)
    assert result.download_result.metadata.video_id == "abc123"
