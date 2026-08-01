"""Tests for provider-neutral ClipperService orchestration."""
import logging
from pathlib import Path
import pytest
import src.clipper.service as service_module
from src.analyzer.models import AnalyzerResult
from src.clipper.backends.base import ClipRenderingBackend
from src.clipper.backends.factory import ClipRenderingBackendFactory
from src.clipper.exceptions import ClipRenderingError
from src.clipper.models import ClipCandidate, ClipConfiguration, ClipFormat, ClipProgress, ClipRequest, ClipStatus, RenderedClip
from src.clipper.service import ClipperService
from src.core.config import ApplicationConfig
from src.core.paths import ProjectPaths
from src.downloader.models import DownloadResult, VideoMetadata
from src.transcript.models import LanguageInfo, TranscriptResult

class FakeBackend(ClipRenderingBackend):
    def __init__(self, fail: bool = False) -> None: self.fail, self.calls = fail, []
    def validate_backend(self, configuration: ClipConfiguration) -> None: pass
    def render_clip(self, request: ClipRequest, candidate: ClipCandidate, progress_callback=None) -> RenderedClip:
        self.calls.append(candidate)
        if self.fail: raise RuntimeError("backend")
        if progress_callback: progress_callback(ClipProgress(ClipStatus.COMPLETED, candidate_id=candidate.candidate_id))
        return RenderedClip(candidate.candidate_id, Path(f"project/output/{candidate.candidate_id}.mp4"), candidate.start_seconds, candidate.end_seconds, ClipFormat.MP4, candidate.end_seconds-candidate.start_seconds)
    def backend_name(self) -> str: return "fake"
    def supported_formats(self) -> frozenset[ClipFormat]: return frozenset({ClipFormat.MP4})

def _request() -> ClipRequest:
    metadata = VideoMetadata("id", "title", 60, None, "url", None); download = DownloadResult(Path("source.mp4"), metadata, False)
    transcript = TranscriptResult(Path("source.mp4"), "text", (), LanguageInfo("en", "English", True), "fake", 0)
    analysis = AnalyzerResult(Path("source.mp4"), (), (), "fake", 0)
    candidates = (ClipCandidate("one", 0, 30, 90, "Hook"), ClipCandidate("two", 30, 60, 80, "Story"))
    return ClipRequest(download, transcript, analysis, candidates, ClipConfiguration(Path("project/output")))
def _service(backend: FakeBackend) -> ClipperService:
    app = ApplicationConfig(ProjectPaths(Path("project"))); factory = ClipRenderingBackendFactory({"fake": lambda: backend}, "fake")
    return ClipperService(app, logging.getLogger("test"), factory, iter((0.0, 2.0)).__next__)

def test_service_renders_multiple_candidates_and_aggregates_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend(); service = _service(backend); events = []
    monkeypatch.setattr(service_module, "validate_clip_request", lambda request, app: request)
    monkeypatch.setattr(service_module, "validate_rendered_clip", lambda rendered, config, app: rendered)
    result = service.render_clips(_request(), events.append)
    assert len(result.rendered_clips) == 2 and len(backend.calls) == 2
    assert events[-1].status is ClipStatus.COMPLETED and events[-1].completed_clips == 2

def test_service_translates_unexpected_backend_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "validate_clip_request", lambda request, app: request)
    with pytest.raises(ClipRenderingError): _service(FakeBackend(True)).render_clips(_request())
