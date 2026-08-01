"""Faster Whisper implementation of the transcript backend contract."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from time import monotonic
from typing import Protocol

from ..exceptions import (
    AudioExtractionError,
    ModelLoadError,
    ModelNotAvailableError,
    TranscriptError,
    TranscriptionFailedError,
    UnsupportedLanguageError,
)
from ..models import (
    LanguageInfo,
    TranscriptConfig,
    TranscriptProgress,
    TranscriptRequest,
    TranscriptResult,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptTask,
)
from ..validator import (
    validate_transcript_config,
    validate_transcript_request,
    validate_transcript_result,
)
from .base import ProgressCallback, TranscriptionBackend


class FasterWhisperModel(Protocol):
    """Minimal Faster Whisper model surface required by this adapter."""

    def transcribe(
        self,
        audio: str,
        **kwargs: object,
    ) -> tuple[Iterable[object], object]:
        """Return provider transcript segments and information."""


ModelFactory = Callable[[str, str, str], FasterWhisperModel]
Clock = Callable[[], float]


class FasterWhisperBackend(TranscriptionBackend):
    """Transcribe local media through a lazily initialized Faster Whisper model."""

    def __init__(
        self,
        logger: logging.Logger,
        model_factory: ModelFactory | None = None,
        clock: Clock = monotonic,
    ) -> None:
        """Create a backend with injectable provider construction and timing.

        Args:
            logger: Application logger supplied by the composition root.
            model_factory: Optional constructor for Faster Whisper model objects.
            clock: Monotonic clock used to report processing duration.
        """
        self._logger = logger
        self._model_factory = model_factory or _default_model_factory
        self._clock = clock
        self._model: FasterWhisperModel | None = None
        self._loaded_model_signature: tuple[str, str, str] | None = None

    def load_model(self, config: TranscriptConfig) -> None:
        """Load the configured model if it is not already reusable."""
        validate_transcript_config(config)
        self._ensure_model_loaded(config)

    def is_model_loaded(self) -> bool:
        """Return whether this backend currently holds a loaded model instance."""
        return self._model is not None

    def transcribe(
        self,
        request: TranscriptRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptResult:
        """Transcribe a validated local media file into public transcript models."""
        validate_transcript_request(request)
        self._emit_progress(progress_callback, TranscriptProgress(status=TranscriptStatus.PREPARING))

        if self._loaded_model_signature != _model_signature(request.config):
            self._emit_progress(
                progress_callback,
                TranscriptProgress(status=TranscriptStatus.LOADING_MODEL),
            )
        self._ensure_model_loaded(request.config)
        self._logger.info(
            "transcription_started",
            extra={"event": "transcription_started", "backend": self.backend_name()},
        )

        started_at = self._clock()
        try:
            segments, info = self._require_model().transcribe(
                str(request.media_path),
                language=request.language_code,
                task=request.task.value,
                word_timestamps=request.config.word_timestamps,
                initial_prompt=request.config.initial_prompt,
            )
            result = self._build_result(request, segments, info, self._clock() - started_at, progress_callback)
        except TranscriptError:
            raise
        except Exception as error:
            self._logger.exception(
                "transcription_provider_failed",
                extra={"event": "transcription_provider_failed", "backend": self.backend_name()},
            )
            raise _translate_transcription_error(error) from None

        validate_transcript_result(result)
        self._emit_progress(progress_callback, TranscriptProgress(status=TranscriptStatus.COMPLETED))
        self._logger.info(
            "transcription_completed",
            extra={
                "event": "transcription_completed",
                "backend": self.backend_name(),
                "segment_count": len(result.segments),
            },
        )
        return result

    def backend_name(self) -> str:
        """Return the stable factory identifier for this backend."""
        return "faster_whisper"

    def supported_formats(self) -> frozenset[str]:
        """Return media suffixes supported by the Faster Whisper adapter."""
        return frozenset({".aac", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4", ".wav", ".webm"})

    def supported_tasks(self) -> frozenset[TranscriptTask]:
        """Return Faster Whisper tasks exposed by the application contract."""
        return frozenset({TranscriptTask.TRANSCRIBE, TranscriptTask.TRANSLATE})

    def _ensure_model_loaded(self, config: TranscriptConfig) -> None:
        """Create a model only when no matching loaded model already exists."""
        signature = _model_signature(config)
        if self._model is not None and self._loaded_model_signature == signature:
            return

        try:
            model = self._model_factory(*signature)
        except TranscriptError:
            raise
        except ModuleNotFoundError as error:
            raise ModelNotAvailableError("Faster Whisper is not installed.") from error
        except Exception as error:
            self._logger.exception(
                "faster_whisper_model_load_failed",
                extra={"event": "model_load_failed", "backend": self.backend_name()},
            )
            raise _translate_model_error(error) from None

        self._model = model
        self._loaded_model_signature = signature
        self._logger.info(
            "faster_whisper_model_loaded",
            extra={"event": "model_loaded", "backend": self.backend_name()},
        )

    def _build_result(
        self,
        request: TranscriptRequest,
        provider_segments: Iterable[object],
        provider_info: object,
        processing_time_seconds: float,
        progress_callback: ProgressCallback | None,
    ) -> TranscriptResult:
        """Convert Faster Whisper output into stable public transcript models."""
        duration_seconds = _optional_float(getattr(provider_info, "duration", None))
        segment_models: list[TranscriptSegment] = []
        for position, provider_segment in enumerate(provider_segments):
            segment = TranscriptSegment(
                segment_id=_required_int(getattr(provider_segment, "id", position), "segment ID"),
                start_seconds=_required_float(getattr(provider_segment, "start", None), "segment start"),
                end_seconds=_required_float(getattr(provider_segment, "end", None), "segment end"),
                text=_required_text(getattr(provider_segment, "text", None)),
            )
            segment_models.append(segment)
            self._emit_segment_progress(progress_callback, segment, duration_seconds)

        language_code = _language_code(provider_info, request)
        return TranscriptResult(
            source_path=request.media_path,
            full_text=" ".join(segment.text.strip() for segment in segment_models),
            segments=tuple(segment_models),
            language=LanguageInfo(
                code=language_code,
                name=language_code,
                detected=request.language_code is None,
                confidence=_optional_float(getattr(provider_info, "language_probability", None)),
            ),
            backend_name=self.backend_name(),
            processing_time_seconds=processing_time_seconds,
            duration_seconds=duration_seconds,
        )

    def _emit_segment_progress(
        self,
        callback: ProgressCallback | None,
        segment: TranscriptSegment,
        duration_seconds: float | None,
    ) -> None:
        """Emit a normalized transcription progress event for one segment."""
        percentage = None
        if duration_seconds is not None and duration_seconds > 0:
            percentage = min(100.0, (segment.end_seconds / duration_seconds) * 100)
        self._emit_progress(
            callback,
            TranscriptProgress(
                status=TranscriptStatus.TRANSCRIBING,
                progress_percentage=percentage,
                processed_seconds=segment.end_seconds,
                total_seconds=duration_seconds,
            ),
        )

    def _emit_progress(self, callback: ProgressCallback | None, progress: TranscriptProgress) -> None:
        """Notify a caller without allowing a callback failure to stop transcription."""
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            self._logger.exception(
                "transcription_progress_callback_failed",
                extra={"event": "progress_callback_failed", "backend": self.backend_name()},
            )

    def _require_model(self) -> FasterWhisperModel:
        """Return the loaded model or raise a stable application exception."""
        if self._model is None:
            raise ModelLoadError("The Faster Whisper model is not loaded.")
        return self._model


def _default_model_factory(model_name: str, device: str, compute_type: str) -> FasterWhisperModel:
    """Create the real Faster Whisper model only when a request first needs it."""
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _model_signature(config: TranscriptConfig) -> tuple[str, str, str]:
    """Return the immutable configuration identity used for model reuse."""
    return (config.model_name, config.device, config.compute_type)


def _language_code(provider_info: object, request: TranscriptRequest) -> str:
    """Choose provider-detected language, falling back to requested language."""
    detected_language = getattr(provider_info, "language", None)
    if isinstance(detected_language, str) and detected_language:
        return detected_language
    if request.language_code is not None:
        return request.language_code
    raise UnsupportedLanguageError("Faster Whisper did not report a detected language.")


def _required_text(value: object) -> str:
    """Return required segment text or raise a transcription failure."""
    if isinstance(value, str) and value.strip():
        return value
    raise TranscriptionFailedError("Faster Whisper returned a segment without text.")


def _required_int(value: object, label: str) -> int:
    """Return a required integer provider value or raise a transcript error."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise TranscriptionFailedError(f"Faster Whisper returned an invalid {label}.")


def _required_float(value: object, label: str) -> float:
    """Return a required numeric provider value or raise a transcript error."""
    numeric_value = _optional_float(value)
    if numeric_value is None:
        raise TranscriptionFailedError(f"Faster Whisper returned an invalid {label}.")
    return numeric_value


def _optional_float(value: object) -> float | None:
    """Convert non-boolean numeric values to floats."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _translate_model_error(error: Exception) -> TranscriptError:
    """Map provider model-loading failures to stable transcript exceptions."""
    message = str(error).lower()
    if "not found" in message or "does not exist" in message:
        return ModelNotAvailableError("The requested Faster Whisper model is unavailable.")
    return ModelLoadError("Faster Whisper could not load the requested model.")


def _translate_transcription_error(error: Exception) -> TranscriptError:
    """Map provider transcription failures to stable transcript exceptions."""
    message = str(error).lower()
    if "language" in message and "support" in message:
        return UnsupportedLanguageError("The requested language is unsupported.")
    if any(keyword in message for keyword in ("audio", "decode", "ffmpeg", "codec")):
        return AudioExtractionError("Audio could not be extracted from the media file.")
    return TranscriptionFailedError("Faster Whisper could not complete transcription.")
