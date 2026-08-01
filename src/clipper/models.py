"""Provider-independent immutable data models for rendered short clips."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.analyzer.models import AnalyzerResult
from src.downloader.models import DownloadResult
from src.transcript.models import TranscriptResult


class ClipStatus(str, Enum):
    """Lifecycle states reported while one or more clips are rendered."""

    PREPARING = "preparing"
    CUTTING = "cutting"
    COMPLETED = "completed"


class ClipFormat(str, Enum):
    """Container formats supported by the clip-cutting contract."""

    MP4 = "mp4"
    WEBM = "webm"
    MOV = "mov"


@dataclass(frozen=True, slots=True)
class ClipConfiguration:
    """Immutable settings controlling rendered clip output.

    Attributes:
        output_directory: Application-controlled destination for rendered clips.
        output_format: Container format used for each rendered clip.
        video_codec: Video codec identifier supplied to the cutting backend.
        audio_codec: Audio codec identifier supplied to the cutting backend.
        overwrite: Whether an existing generated output may be replaced.
        include_audio: Whether rendered clips include their source audio stream.
    """

    output_directory: Path
    output_format: ClipFormat = ClipFormat.MP4
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    overwrite: bool = False
    include_audio: bool = True


@dataclass(frozen=True, slots=True)
class ClipCandidate:
    """A selected timestamp range ready to be rendered as a short clip.

    Attributes:
        candidate_id: Stable identifier for this rendered-clip request.
        start_seconds: Inclusive source-media start timestamp.
        end_seconds: Exclusive source-media end timestamp.
        score: Analyzer-provided suitability score retained for traceability.
        reason: Human-readable explanation for selection.
        title_hint: Optional working title for a future metadata module.
    """

    candidate_id: str
    start_seconds: float
    end_seconds: float
    score: float
    reason: str
    title_hint: str | None = None


@dataclass(frozen=True, slots=True)
class ClipRequest:
    """Input contract for rendering analyzer-selected clips from one download.

    Attributes:
        download_result: Completed downloader output that identifies source media.
        transcript_result: Timestamped transcript retained for downstream context.
        analyzer_result: Analysis result that produced the selected moments.
        candidates: Candidate ranges selected for rendering in this request.
        configuration: Immutable output and encoding settings.
    """

    download_result: DownloadResult
    transcript_result: TranscriptResult
    analyzer_result: AnalyzerResult
    candidates: tuple[ClipCandidate, ...]
    configuration: ClipConfiguration


@dataclass(frozen=True, slots=True)
class RenderedClip:
    """A single successfully rendered output clip.

    Attributes:
        candidate_id: Identifier of the source candidate.
        output_path: Local path to the rendered media file.
        start_seconds: Source-media start timestamp used for rendering.
        end_seconds: Source-media end timestamp used for rendering.
        output_format: Container format of the output media.
        duration_seconds: Duration reported for the rendered clip.
    """

    candidate_id: str
    output_path: Path
    start_seconds: float
    end_seconds: float
    output_format: ClipFormat
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class ClipResult:
    """Completed output from one clip-cutting operation.

    Attributes:
        source_path: Original downloaded media path.
        rendered_clips: Successfully rendered clips in request order.
        processing_time_seconds: Elapsed time spent by the cutting operation.
    """

    source_path: Path
    rendered_clips: tuple[RenderedClip, ...]
    processing_time_seconds: float


@dataclass(frozen=True, slots=True)
class ClipProgress:
    """A normalized progress update emitted during clip rendering.

    Attributes:
        status: Current cutting lifecycle state.
        completed_clips: Number of clips rendered so far.
        total_clips: Total clips requested for rendering.
        candidate_id: Optional candidate currently being rendered.
        message: Optional safe display message.
    """

    status: ClipStatus
    completed_clips: int | None = None
    total_clips: int | None = None
    candidate_id: str | None = None
    message: str | None = None


ProgressCallback = Callable[[ClipProgress], None]
