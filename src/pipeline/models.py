"""Immutable application models for end-to-end Short generation orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from src.analyzer.models import AnalysisConfig, AnalyzerResult
from src.clipper.models import ClipConfiguration, ClipResult
from src.downloader.models import DownloadConfig, DownloadResult
from src.transcript.models import TranscriptConfig, TranscriptResult


class PipelineStage(str, Enum):
    """Workflow stages coordinated by the pipeline service."""

    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    RENDERING = "rendering"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class PipelineRequest:
    """Immutable configuration for one complete YouTube-to-clips workflow.

    Attributes:
        source_url: YouTube URL supplied by the caller.
        download_config: Settings passed to the downloader service.
        transcript_config: Settings passed to the transcript service.
        analysis_config: Settings passed to the analyzer service.
        clip_configuration: Settings passed to the clip-rendering service.
        transcription_backend_name: Optional selected transcript backend identifier.
        analyzer_name: Optional selected analysis-provider identifier.
    """

    source_url: str
    download_config: DownloadConfig
    transcript_config: TranscriptConfig
    analysis_config: AnalysisConfig
    clip_configuration: ClipConfiguration
    transcription_backend_name: str | None = None
    analyzer_name: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineProgress:
    """Normalized progress update spanning the complete pipeline workflow.

    Attributes:
        stage: Stage currently being processed.
        completed_stages: Number of workflow stages completed so far.
        total_stages: Total stages in this pipeline version.
        stage_progress_percentage: Optional percentage reported by the active stage.
        message: Optional safe display message.
    """

    stage: PipelineStage
    completed_stages: int
    total_stages: int
    stage_progress_percentage: float | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Immutable result from one completed end-to-end generation workflow.

    Attributes:
        download_result: Source-media result from the downloader stage.
        transcript_result: Timestamped transcript from the transcript stage.
        analyzer_result: Ranked clip candidates from the analyzer stage.
        clip_result: Rendered output clips from the clipper stage.
        processing_time_seconds: Total elapsed pipeline processing duration.
    """

    download_result: DownloadResult
    transcript_result: TranscriptResult
    analyzer_result: AnalyzerResult
    clip_result: ClipResult
    processing_time_seconds: float


ProgressCallback = Callable[[PipelineProgress], None]
