"""Tests for provider-neutral transcript service orchestration."""

import logging
from pathlib import Path

import pytest

from src.core.config import ApplicationConfig
from src.core.paths import ProjectPaths
from src.transcript.backends.base import ProgressCallback, TranscriptionBackend
from src.transcript.backends.factory import TranscriptionBackendFactory
from src.transcript.exceptions import TranscriptionCancelledError, TranscriptionFailedError
from src.transcript.models import (
    LanguageInfo,
    TranscriptConfig,
    TranscriptProgress,
    TranscriptRequest,
    TranscriptResult,
    TranscriptStatus,
    TranscriptTask,
)
from src.transcript.service import TranscriptService
import src.transcript.service as service_module


class RecordingBackend(TranscriptionBackend):
    """Provider-free backend recording service delegation."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.requests: list[TranscriptRequest] = []

    def load_model(self, config: TranscriptConfig) -> None:
        """Satisfy the contract without provider work."""

    def is_model_loaded(self) -> bool:
        """Report the fake backend as ready."""
        return True

    def transcribe(
        self, request: TranscriptRequest, progress_callback: ProgressCallback | None = None
    ) -> TranscriptResult:
        """Record delegation and return a deterministic result or fail."""
        self.requests.append(request)
        if self.should_fail:
            raise RuntimeError("provider failed")
        if progress_callback is not None:
            progress_callback(TranscriptProgress(status=TranscriptStatus.TRANSCRIBING))
        return _result()

    def backend_name(self) -> str:
        """Return the test backend identifier."""
        return "recording"

    def supported_formats(self) -> frozenset[str]:
        """Return a representative media suffix."""
        return frozenset({".mp4"})

    def supported_tasks(self) -> frozenset[TranscriptTask]:
        """Return the supported task."""
        return frozenset({TranscriptTask.TRANSCRIBE})


def test_service_validates_selects_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service orchestrates an injected default backend without provider logic."""
    backend = RecordingBackend()
    service = _service(backend)
    request = _request()
    events: list[TranscriptProgress] = []
    monkeypatch.setattr(service_module, "validate_transcript_request", lambda value: value)
    monkeypatch.setattr(service_module, "validate_transcript_result", lambda value: value)

    result = service.transcribe(request, events.append)

    assert result is not None
    assert backend.requests == [request]
    assert events == [TranscriptProgress(status=TranscriptStatus.TRANSCRIBING)]


def test_service_translates_unexpected_backend_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raw provider errors cannot escape the service boundary."""
    service = _service(RecordingBackend(should_fail=True))
    monkeypatch.setattr(service_module, "validate_transcript_request", lambda value: value)
    with pytest.raises(TranscriptionFailedError):
        service.transcribe(_request())


def test_service_preserves_application_backend_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Known transcript exceptions remain visible to the caller unchanged."""
    backend = RecordingBackend()
    backend.transcribe = lambda *_: (_ for _ in ()).throw(TranscriptionCancelledError("cancelled"))  # type: ignore[method-assign]
    service = _service(backend)
    monkeypatch.setattr(service_module, "validate_transcript_request", lambda value: value)
    with pytest.raises(TranscriptionCancelledError):
        service.transcribe(_request())


def _service(backend: RecordingBackend) -> TranscriptService:
    """Build a service with a local path config and injected backend instance."""
    factory = TranscriptionBackendFactory({"recording": lambda: backend}, "recording")
    return TranscriptService(
        ApplicationConfig(paths=ProjectPaths(Path("project"))),
        logging.getLogger("tests.transcript.service"),
        factory,
    )


def _request() -> TranscriptRequest:
    """Build a request without touching a real media file."""
    return TranscriptRequest(Path("video.mp4"), TranscriptConfig(model_name="small"))


def _result() -> TranscriptResult:
    """Build a valid provider-independent transcript result."""
    return TranscriptResult(
        source_path=Path("video.mp4"),
        full_text="",
        segments=(),
        language=LanguageInfo("en", "English", detected=True),
        backend_name="recording",
        processing_time_seconds=0.0,
    )
