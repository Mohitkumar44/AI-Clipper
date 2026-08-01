"""Immutable public data models for timestamped media transcription."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class TranscriptStatus(str, Enum):
    """Lifecycle states reported by a transcription operation."""

    PREPARING = "preparing"
    LOADING_MODEL = "loading_model"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"


class TranscriptTask(str, Enum):
    """Speech-recognition tasks that a backend may support."""

    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"


@dataclass(frozen=True, slots=True)
class TranscriptConfig:
    """Immutable settings that control a transcription request.

    Attributes:
        model_name: Backend model identifier selected by application configuration.
        device: Requested compute device, such as ``cpu`` or ``cuda``.
        compute_type: Backend compute precision, such as ``int8`` or ``float16``.
        word_timestamps: Whether the caller requests word-level timing data.
        initial_prompt: Optional recognition context supplied to the backend.
    """

    model_name: str
    device: str = "cpu"
    compute_type: str = "int8"
    word_timestamps: bool = False
    initial_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptRequest:
    """Input contract for transcribing one local media file.

    Attributes:
        media_path: Local video or audio file to transcribe.
        config: Immutable settings for this request.
        language_code: Optional requested language; ``None`` permits detection.
        task: Requested transcription or translation task.
        backend_name: Optional configured backend identifier.
    """

    media_path: Path
    config: TranscriptConfig
    language_code: str | None = None
    task: TranscriptTask = TranscriptTask.TRANSCRIBE
    backend_name: str | None = None


@dataclass(frozen=True, slots=True)
class LanguageInfo:
    """Language selected or detected during a transcription operation."""

    code: str
    name: str
    detected: bool
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """A timestamped unit of recognized speech."""

    segment_id: int
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class TranscriptProgress:
    """A status update emitted while a transcription request is processed."""

    status: TranscriptStatus
    progress_percentage: float | None = None
    processed_seconds: float | None = None
    total_seconds: float | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class TranscriptResult:
    """Completed transcript returned to later analysis and editing modules."""

    source_path: Path
    full_text: str
    segments: tuple[TranscriptSegment, ...]
    language: LanguageInfo
    backend_name: str
    processing_time_seconds: float
    duration_seconds: float | None = None
