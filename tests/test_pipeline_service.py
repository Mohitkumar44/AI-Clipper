"""Tests for in-memory PipelineService orchestration."""

import logging
from pathlib import Path

import pytest

from src.analyzer.models import AnalysisConfig, AnalysisProgress, AnalysisStatus, AnalyzerResult, ClipCandidate as AnalyzerClipCandidate
from src.clipper.models import ClipConfiguration, ClipProgress, ClipResult, ClipStatus, RenderedClip
from src.downloader.models import DownloadConfig, DownloadProgress, DownloadResult, DownloadStatus, VideoMetadata
from src.pipeline.exceptions import AnalysisStageError, ClipRenderingStageError, DownloadStageError, TranscriptStageError
from src.pipeline.models import PipelineRequest, PipelineStage
from src.pipeline.service import PipelineService
from src.transcript.models import LanguageInfo, TranscriptConfig, TranscriptProgress, TranscriptResult, TranscriptStatus


class FakeDownloader:
    """In-memory downloader fake that never contacts YouTube."""
    def __init__(self, error: Exception | None = None) -> None: self.error = error
    def download_video(self, request, callback=None) -> DownloadResult:
        if self.error: raise self.error
        if callback: callback(DownloadProgress(DownloadStatus.DOWNLOADING, 50, 100))
        return _download()

class FakeTranscript:
    """In-memory transcript fake that never loads a model or media."""
    def __init__(self, error: Exception | None = None) -> None: self.error = error
    def transcribe(self, request, callback=None) -> TranscriptResult:
        if self.error: raise self.error
        if callback: callback(TranscriptProgress(TranscriptStatus.TRANSCRIBING, 50))
        return _transcript()

class FakeAnalyzer:
    """In-memory analyzer fake that never calls an AI provider."""
    def __init__(self, error: Exception | None = None) -> None: self.error = error
    def analyze(self, request, callback=None) -> AnalyzerResult:
        if self.error: raise self.error
        if callback: callback(AnalysisProgress(AnalysisStatus.ANALYZING, 50))
        return _analysis()

class FakeClipper:
    """In-memory clipper fake that never invokes FFmpeg."""
    def __init__(self, error: Exception | None = None) -> None: self.error = error
    def render_clips(self, request, callback=None) -> ClipResult:
        if self.error: raise self.error
        if callback: callback(ClipProgress(ClipStatus.CUTTING, 0, 1, "candidate-1"))
        return ClipResult(Path("source.mp4"), (RenderedClip("candidate-1", Path("output/clip.mp4"), 0, 30, request.configuration.output_format, 30),), 0)

def _request() -> PipelineRequest:
    """Build a pipeline request without touching any external system."""
    return PipelineRequest("https://www.youtube.com/watch?v=abc123", DownloadConfig(Path("downloads")), TranscriptConfig("small"), AnalysisConfig(), ClipConfiguration(Path("output")))

def _service(download=None, transcript=None, analyzer=None, clipper=None) -> PipelineService:
    """Build a pipeline service with all dependencies replaced by fakes."""
    return PipelineService(download or FakeDownloader(), transcript or FakeTranscript(), analyzer or FakeAnalyzer(), clipper or FakeClipper(), logging.getLogger("test.pipeline"), iter((0.0, 1.0)).__next__)

def _download() -> DownloadResult:
    metadata = VideoMetadata("abc123", "Title", 60, None, "url", None)
    return DownloadResult(Path("source.mp4"), metadata, False)

def _transcript() -> TranscriptResult:
    return TranscriptResult(Path("source.mp4"), "Text", (), LanguageInfo("en", "English", True), "fake", 0)

def _analysis() -> AnalyzerResult:
    candidate = AnalyzerClipCandidate("candidate-1", 0, 30, 90, "Hook")
    return AnalyzerResult(Path("source.mp4"), (candidate,), (), "fake", 0)

def test_pipeline_runs_all_stages_and_forwards_progress() -> None:
    """Successful orchestration returns immutable outputs from all fake services."""
    events = []
    result = _service().run(_request(), events.append)
    assert len(result.clip_result.rendered_clips) == 1
    assert events[-1].stage is PipelineStage.COMPLETED

@pytest.mark.parametrize(
    ("service", "expected"),
    [
        (_service(download=FakeDownloader(RuntimeError("download"))), DownloadStageError),
        (_service(transcript=FakeTranscript(RuntimeError("transcript"))), TranscriptStageError),
        (_service(analyzer=FakeAnalyzer(RuntimeError("analysis"))), AnalysisStageError),
        (_service(clipper=FakeClipper(RuntimeError("clip"))), ClipRenderingStageError),
    ],
)
def test_pipeline_translates_stage_failures(service: PipelineService, expected: type[Exception]) -> None:
    """Raw stage exceptions cannot escape the pipeline boundary."""
    with pytest.raises(expected):
        service.run(_request())

def test_pipeline_isolates_progress_callback_failures() -> None:
    """UI callback failures never interrupt an otherwise successful workflow."""
    result = _service().run(_request(), lambda _: (_ for _ in ()).throw(RuntimeError("callback")))
    assert result.clip_result.rendered_clips[0].candidate_id == "candidate-1"
