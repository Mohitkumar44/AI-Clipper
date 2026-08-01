"""Tests for Faster Whisper adaptation without loading a real model."""

import logging
from pathlib import Path

import pytest

from src.transcript.backends import faster_whisper
from src.transcript.backends.faster_whisper import FasterWhisperBackend
from src.transcript.exceptions import (
    AudioExtractionError,
    ModelNotAvailableError,
    TranscriptionFailedError,
    UnsupportedLanguageError,
)
from src.transcript.models import (
    TranscriptConfig,
    TranscriptProgress,
    TranscriptRequest,
    TranscriptStatus,
    TranscriptTask,
)


class ProviderSegment:
    """Minimal Faster Whisper segment substitute."""

    def __init__(self, segment_id: int, start: float, end: float, text: str) -> None:
        self.id = segment_id
        self.start = start
        self.end = end
        self.text = text


class ProviderInfo:
    """Minimal Faster Whisper transcription-info substitute."""

    duration = 10.0
    language = "en"
    language_probability = 0.95


class FakeModel:
    """In-memory model substitute recording every transcribe call."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, object]]] = []

    def transcribe(self, audio: str, **kwargs: object) -> tuple[list[ProviderSegment], ProviderInfo]:
        """Return deterministic output or raise a controlled provider error."""
        self.calls.append((audio, kwargs))
        if self.error is not None:
            raise self.error
        return [ProviderSegment(0, 0.0, 5.0, " Hello world ")], ProviderInfo()


def test_backend_loads_lazily_reuses_model_and_reports_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No model is constructed until transcription, then matching config reuses it."""
    models: list[FakeModel] = []

    def model_factory(*_: str) -> FakeModel:
        model = FakeModel()
        models.append(model)
        return model

    backend = FasterWhisperBackend(logging.getLogger("tests.faster"), model_factory, _clock())
    monkeypatch.setattr(faster_whisper, "validate_transcript_request", lambda value: value)
    request = _request()
    progress_events: list[TranscriptProgress] = []

    assert backend.is_model_loaded() is False
    first_result = backend.transcribe(request, progress_events.append)
    second_result = backend.transcribe(request)

    assert len(models) == 1
    assert backend.is_model_loaded() is True
    assert first_result.full_text == "Hello world"
    assert second_result.language.code == "en"
    assert models[0].calls[0][1]["task"] == "transcribe"
    assert [event.status for event in progress_events] == [
        TranscriptStatus.PREPARING,
        TranscriptStatus.LOADING_MODEL,
        TranscriptStatus.TRANSCRIBING,
        TranscriptStatus.COMPLETED,
    ]


def test_backend_translates_provider_audio_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider decoder failures become a stable audio extraction exception."""
    backend = FasterWhisperBackend(
        logging.getLogger("tests.faster"),
        lambda *_: FakeModel(RuntimeError("could not decode audio")),
    )
    monkeypatch.setattr(faster_whisper, "validate_transcript_request", lambda value: value)
    with pytest.raises(AudioExtractionError):
        backend.transcribe(_request())


def test_backend_translates_missing_provider_dependency() -> None:
    """A missing Faster Whisper import is exposed as a model availability error."""
    def missing_model_factory(*_: str) -> FakeModel:
        raise ModuleNotFoundError("faster_whisper")

    backend = FasterWhisperBackend(logging.getLogger("tests.faster"), missing_model_factory)
    with pytest.raises(ModelNotAvailableError):
        backend.load_model(TranscriptConfig(model_name="small"))


def test_backend_reloads_when_model_configuration_changes() -> None:
    """A changed model signature creates a new provider model exactly once."""
    created: list[FakeModel] = []
    backend = FasterWhisperBackend(
        logging.getLogger("tests.faster"),
        lambda *_: created.append(FakeModel()) or created[-1],
    )
    backend.load_model(TranscriptConfig(model_name="small"))
    backend.load_model(TranscriptConfig(model_name="medium"))
    assert len(created) == 2


def test_backend_translates_model_and_language_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider-specific failures map to stable model and language exceptions."""
    monkeypatch.setattr(faster_whisper, "validate_transcript_request", lambda value: value)
    model_load_backend = FasterWhisperBackend(
        logging.getLogger("tests.faster"),
        lambda *_: (_ for _ in ()).throw(RuntimeError("model not found")),
    )
    with pytest.raises(ModelNotAvailableError):
        model_load_backend.load_model(TranscriptConfig(model_name="small"))

    language_backend = FasterWhisperBackend(
        logging.getLogger("tests.faster"),
        lambda *_: FakeModel(RuntimeError("language not supported")),
    )
    with pytest.raises(UnsupportedLanguageError):
        language_backend.transcribe(_request())


def test_backend_handles_progress_callback_and_invalid_provider_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken callback is isolated and malformed provider data fails safely."""
    monkeypatch.setattr(faster_whisper, "validate_transcript_request", lambda value: value)
    backend = FasterWhisperBackend(logging.getLogger("tests.faster"), lambda *_: FakeModel())
    backend.transcribe(_request(), lambda _: (_ for _ in ()).throw(RuntimeError("callback")))

    class EmptyTextModel(FakeModel):
        def transcribe(self, audio: str, **kwargs: object) -> tuple[list[ProviderSegment], ProviderInfo]:
            return [ProviderSegment(0, 0.0, 1.0, "")], ProviderInfo()

    invalid_backend = FasterWhisperBackend(
        logging.getLogger("tests.faster"), lambda *_: EmptyTextModel()
    )
    with pytest.raises(TranscriptionFailedError):
        invalid_backend.transcribe(_request())


def test_backend_rejects_missing_detected_language(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detection mode requires the provider to report a language code."""
    monkeypatch.setattr(faster_whisper, "validate_transcript_request", lambda value: value)

    class MissingLanguageInfo(ProviderInfo):
        language = None

    class MissingLanguageModel(FakeModel):
        def transcribe(self, audio: str, **kwargs: object) -> tuple[list[ProviderSegment], MissingLanguageInfo]:
            return [ProviderSegment(0, 0.0, 1.0, "Text")], MissingLanguageInfo()

    backend = FasterWhisperBackend(logging.getLogger("tests.faster"), lambda *_: MissingLanguageModel())
    with pytest.raises(UnsupportedLanguageError):
        backend.transcribe(_request())


def test_backend_exposes_provider_neutral_capabilities() -> None:
    """Capabilities remain available without constructing a model."""
    backend = FasterWhisperBackend(logging.getLogger("tests.faster"), lambda *_: FakeModel())
    assert backend.backend_name() == "faster_whisper"
    assert ".mp4" in backend.supported_formats()
    assert TranscriptTask.TRANSLATE in backend.supported_tasks()


def _request() -> TranscriptRequest:
    """Build a request whose validation is mocked to avoid media access."""
    return TranscriptRequest(Path("video.mp4"), TranscriptConfig(model_name="small"))


def _clock():
    """Return a deterministic monotonic clock for processing-time assertions."""
    values = iter((10.0, 12.0, 20.0, 23.0))
    return lambda: next(values)
