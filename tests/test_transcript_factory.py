"""Tests for dependency-injected transcription backend selection."""

from pathlib import Path

import pytest

from src.transcript.backends.base import TranscriptionBackend
from src.transcript.backends.factory import TranscriptionBackendFactory
from src.transcript.exceptions import (
    InvalidTranscriptRequestError,
    ModelNotAvailableError,
    TranscriptionFailedError,
)
from src.transcript.models import (
    LanguageInfo,
    TranscriptConfig,
    TranscriptRequest,
    TranscriptResult,
    TranscriptTask,
)


class FakeBackend(TranscriptionBackend):
    """Minimal provider-free backend for factory tests."""

    def load_model(self, config: TranscriptConfig) -> None:
        """Satisfy the abstract contract without model work."""

    def is_model_loaded(self) -> bool:
        """Report a loaded fake model."""
        return True

    def transcribe(self, request: TranscriptRequest, progress_callback: object = None) -> TranscriptResult:
        """Return a deterministic empty transcript."""
        return TranscriptResult(
            source_path=Path("video.mp4"),
            full_text="",
            segments=(),
            language=LanguageInfo("en", "English", detected=True),
            backend_name=self.backend_name(),
            processing_time_seconds=0.0,
        )

    def backend_name(self) -> str:
        """Return the test backend name."""
        return "fake"

    def supported_formats(self) -> frozenset[str]:
        """Return a representative supported format."""
        return frozenset({".mp4"})

    def supported_tasks(self) -> frozenset[TranscriptTask]:
        """Return the supported fake task."""
        return frozenset({TranscriptTask.TRANSCRIBE})


def test_factory_registers_and_creates_backend_instances() -> None:
    """Factories are called per retrieval rather than shared globally."""
    factory = TranscriptionBackendFactory()
    factory.register_backend("fake", FakeBackend)
    assert factory.available_backends() == ("fake",)
    assert isinstance(factory.get_backend("fake"), FakeBackend)
    assert factory.get_backend("fake") is not factory.get_backend("fake")


def test_factory_returns_configured_default_backend() -> None:
    """Default selection remains part of injected factory configuration."""
    factory = TranscriptionBackendFactory({"fake": FakeBackend}, default_backend_name="fake")
    assert factory.get_default_backend().backend_name() == "fake"


def test_factory_rejects_unknown_and_invalid_backend_names() -> None:
    """Selection failures use transcript-domain exceptions only."""
    factory = TranscriptionBackendFactory()
    with pytest.raises(ModelNotAvailableError):
        factory.get_default_backend()
    with pytest.raises(ModelNotAvailableError):
        factory.get_backend("missing")
    with pytest.raises(InvalidTranscriptRequestError):
        factory.register_backend("Invalid Name", FakeBackend)


def test_factory_rejects_invalid_default_and_factory_results() -> None:
    """Misconfigured default and incompatible factory outputs fail safely."""
    with pytest.raises(ModelNotAvailableError):
        TranscriptionBackendFactory({"fake": FakeBackend}, default_backend_name="missing")

    factory = TranscriptionBackendFactory({"wrong": lambda: object()})
    with pytest.raises(TranscriptionFailedError):
        factory.get_backend("wrong")


def test_factory_translates_constructor_and_registration_failures() -> None:
    """Unexpected constructor errors never escape as provider exceptions."""
    factory = TranscriptionBackendFactory()
    with pytest.raises(InvalidTranscriptRequestError):
        factory.register_backend("fake", object())  # type: ignore[arg-type]
    factory.register_backend("broken", lambda: (_ for _ in ()).throw(RuntimeError("failure")))
    with pytest.raises(TranscriptionFailedError):
        factory.get_backend("broken")
