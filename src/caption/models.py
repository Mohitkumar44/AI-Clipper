"""Immutable application models for generated short-form caption data."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from src.clipper.models import RenderedClip
from src.transcript.models import TranscriptResult


class CaptionStatus(str, Enum):
    """Lifecycle states reported while caption data is generated."""

    PREPARING = "preparing"
    SEGMENTING = "segmenting"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class CaptionConfiguration:
    """Immutable settings controlling readable caption segmentation.

    Attributes:
        maximum_characters_per_line: Maximum characters permitted in one line.
        maximum_lines_per_caption: Maximum lines grouped in one caption segment.
    """

    maximum_characters_per_line: int = 42
    maximum_lines_per_caption: int = 2


@dataclass(frozen=True, slots=True)
class CaptionRequest:
    """Input contract for generating caption data for one rendered clip.

    Attributes:
        transcript_result: Timestamped source transcript.
        rendered_clip: Rendered clip whose source-time range scopes captions.
        configuration: Immutable caption segmentation settings.
    """

    transcript_result: TranscriptResult
    rendered_clip: RenderedClip
    configuration: CaptionConfiguration


@dataclass(frozen=True, slots=True)
class CaptionSegment:
    """One timestamp-preserving caption segment made up of display lines.

    Attributes:
        start_seconds: Original transcript start timestamp.
        end_seconds: Original transcript end timestamp.
        lines: Immutable display lines for this caption segment.
    """

    start_seconds: float
    end_seconds: float
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaptionProgress:
    """Normalized progress update emitted during caption generation.

    Attributes:
        status: Current caption-generation lifecycle state.
        processed_segments: Transcript segments processed so far.
        total_segments: Total transcript segments considered for the clip.
    """

    status: CaptionStatus
    processed_segments: int | None = None
    total_segments: int | None = None


@dataclass(frozen=True, slots=True)
class CaptionResult:
    """Immutable generated caption data associated with a rendered clip.

    Attributes:
        rendered_clip: Clip for which captions were generated.
        segments: Timestamp-preserving caption segments in source order.
    """

    rendered_clip: RenderedClip
    segments: tuple[CaptionSegment, ...]


ProgressCallback = Callable[[CaptionProgress], None]
