"""Provider-independent data models for transcript-based clip analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.transcript.models import TranscriptResult


class AnalysisStatus(str, Enum):
    """Lifecycle states reported during a clip-analysis operation."""

    PREPARING = "preparing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"


class ViralMomentType(str, Enum):
    """Content patterns that can make a segment suitable for short-form video."""

    HOOK = "hook"
    INSIGHT = "insight"
    STORY = "story"
    EMOTION = "emotion"
    HUMOR = "humor"
    CONTROVERSY = "controversy"


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Immutable settings that control transcript analysis.

    Attributes:
        maximum_candidates: Maximum number of candidate clips to return.
        minimum_clip_duration_seconds: Minimum allowed candidate duration.
        maximum_clip_duration_seconds: Maximum allowed candidate duration.
        target_language_code: Language used for generated analysis text.
        custom_instructions: Optional user-provided analysis guidance.
        include_transcript_excerpt: Whether results include supporting excerpts.
    """

    maximum_candidates: int = 10
    minimum_clip_duration_seconds: float = 15.0
    maximum_clip_duration_seconds: float = 60.0
    target_language_code: str | None = None
    custom_instructions: str | None = None
    include_transcript_excerpt: bool = True


@dataclass(frozen=True, slots=True)
class ClipCandidate:
    """A ranked timestamp range proposed for short-form video generation.

    Attributes:
        candidate_id: Stable identifier within one analysis result.
        start_seconds: Candidate start time in the source media.
        end_seconds: Candidate end time in the source media.
        score: Provider-normalized suitability score.
        reason: Concise explanation for the candidate selection.
        hook: Opening line or summary intended to capture viewer attention.
        transcript_excerpt: Optional supporting transcript text.
    """

    candidate_id: str
    start_seconds: float
    end_seconds: float
    score: float
    reason: str
    hook: str | None = None
    transcript_excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class ViralMoment:
    """A classified high-potential moment identified during analysis.

    Attributes:
        moment_id: Stable identifier within one analysis result.
        moment_type: Content pattern detected in the moment.
        start_seconds: Moment start time in the source media.
        end_seconds: Moment end time in the source media.
        score: Provider-normalized viral-potential score.
        explanation: Human-readable reason for the classification.
    """

    moment_id: str
    moment_type: ViralMomentType
    start_seconds: float
    end_seconds: float
    score: float
    explanation: str


@dataclass(frozen=True, slots=True)
class AnalyzerRequest:
    """Input contract for analyzing a completed transcript.

    Attributes:
        source_path: Local source-media path associated with the transcript.
        transcript: Timestamped transcript supplied by the transcript module.
        config: Immutable analysis settings for this request.
        analyzer_name: Optional configured analyzer identifier.
    """

    source_path: Path
    transcript: TranscriptResult
    config: AnalysisConfig
    analyzer_name: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisProgress:
    """A status update emitted while an analysis request is processed.

    Attributes:
        status: Current lifecycle state.
        progress_percentage: Optional estimated completion percentage.
        processed_segments: Number of transcript segments processed.
        total_segments: Total available transcript segments.
        message: Optional safe display message.
    """

    status: AnalysisStatus
    progress_percentage: float | None = None
    processed_segments: int | None = None
    total_segments: int | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    """Provider-independent output from one transcript analysis operation.

    Attributes:
        source_path: Local media path associated with this result.
        candidates: Ranked clip candidates for later video cutting.
        viral_moments: Classified moments supporting the recommendations.
        analyzer_name: Stable identifier of the analyzer implementation used.
        processing_time_seconds: Elapsed analysis time.
    """

    source_path: Path
    candidates: tuple[ClipCandidate, ...]
    viral_moments: tuple[ViralMoment, ...]
    analyzer_name: str
    processing_time_seconds: float
