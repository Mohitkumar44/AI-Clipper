"""Tests for FFmpeg backend using injected subprocess fakes only."""
import logging
from pathlib import Path
import subprocess
import pytest
from src.analyzer.models import AnalyzerResult
from src.clipper.backends.ffmpeg_backend import FFmpegClipRenderingBackend
from src.clipper.exceptions import ClipRenderingError, FFmpegNotFoundError
from src.clipper.models import ClipCandidate, ClipConfiguration, ClipFormat, ClipRequest, ClipStatus
from src.downloader.models import DownloadResult, VideoMetadata
from src.transcript.models import LanguageInfo, TranscriptResult

def _request() -> ClipRequest:
    metadata = VideoMetadata("id", "title", 60, None, "https://youtube.com/watch?v=id", None)
    download = DownloadResult(Path("source.mp4"), metadata, False)
    transcript = TranscriptResult(Path("source.mp4"), "text", (), LanguageInfo("en", "English", True), "fake", 0)
    analysis = AnalyzerResult(Path("source.mp4"), (), (), "fake", 0)
    return ClipRequest(download, transcript, analysis, (ClipCandidate("candidate-1", 0, 30, 90, "Hook"),), ClipConfiguration(Path("output")))

class Runner:
    def __init__(self, returncode: int = 0, error: Exception | None = None) -> None: self.returncode, self.error, self.calls = returncode, error, []
    def __call__(self, arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((arguments, kwargs))
        if self.error: raise self.error
        return subprocess.CompletedProcess(arguments, self.returncode, "", "")

def test_ffmpeg_backend_renders_with_safe_argument_list(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Runner(); backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 5, runner)
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    events = []; rendered = backend.render_clip(_request(), _request().candidates[0], events.append)
    render_arguments, kwargs = runner.calls[1]
    assert rendered.duration_seconds == 30
    assert kwargs["shell"] is False and "-ss" in render_arguments and "-t" in render_arguments
    assert [event.status for event in events] == [ClipStatus.CUTTING, ClipStatus.COMPLETED]

def test_ffmpeg_backend_translates_runner_failures() -> None:
    missing = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, Runner(error=FileNotFoundError()))
    with pytest.raises(FFmpegNotFoundError): missing.validate_backend(ClipConfiguration(Path("output")))
    failed = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, Runner(returncode=1))
    with pytest.raises(ClipRenderingError): failed.validate_backend(ClipConfiguration(Path("output")))

def test_ffmpeg_backend_translates_render_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = Runner(); backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, runner)
    monkeypatch.setattr(Path, "is_file", lambda _: False)
    with pytest.raises(Exception): backend.render_clip(_request(), _request().candidates[0])

def test_ffmpeg_backend_constructor_and_process_error_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(Exception): FFmpegClipRenderingBackend("ffmpeg", logging.getLogger("test"), 1)  # type: ignore[arg-type]
    with pytest.raises(Exception): FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 0)
    timeout_backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, Runner(error=subprocess.TimeoutExpired(["ffmpeg"], 1)))
    with pytest.raises(ClipRenderingError): timeout_backend.validate_backend(ClipConfiguration(Path("output")))
    runner = Runner(); backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, runner)
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    calls = 0
    def process(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls; calls += 1
        return subprocess.CompletedProcess(arguments, 0 if calls == 1 else 1, "", "")
    backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, process)
    with pytest.raises(ClipRenderingError): backend.render_clip(_request(), _request().candidates[0])

def test_ffmpeg_backend_render_execution_errors_and_callback_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    calls = 0
    def missing_on_render(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls; calls += 1
        if calls == 2: raise FileNotFoundError()
        return subprocess.CompletedProcess(arguments, 0, "", "")
    backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, missing_on_render)
    with pytest.raises(FFmpegNotFoundError): backend.render_clip(_request(), _request().candidates[0])
    runner = Runner(); backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, runner)
    rendered = backend.render_clip(_request(), _request().candidates[0], lambda _: (_ for _ in ()).throw(RuntimeError("callback")))
    assert rendered.output_path.name.startswith("clip_")

def test_ffmpeg_backend_audio_policy_and_format_helpers() -> None:
    request = _request()
    silent_request = type(request)(request.download_result, request.transcript_result, request.analyzer_result, request.candidates, ClipConfiguration(Path("output"), include_audio=False))
    backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, Runner())
    arguments = backend._build_ffmpeg_arguments(silent_request, silent_request.candidates[0], Path("output/clip.mp4"))
    assert "-an" in arguments and backend.backend_name() == "ffmpeg" and ClipFormat.MP4 in backend.supported_formats()

def test_ffmpeg_backend_covers_remaining_process_and_validation_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(Exception): FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, Runner()).validate_backend("bad")  # type: ignore[arg-type]
    backend = FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, Runner())
    with pytest.raises(Exception): backend._validate_output_path(Path("outside/clip.mp4"), ClipConfiguration(Path("output")))
    calls = 0
    def errors(arguments: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls; calls += 1
        if calls == 2: raise subprocess.TimeoutExpired(arguments, 1)
        return subprocess.CompletedProcess(arguments, 0, "", "")
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    with pytest.raises(ClipRenderingError): FFmpegClipRenderingBackend(Path("ffmpeg"), logging.getLogger("test"), 1, errors).render_clip(_request(), _request().candidates[0])
