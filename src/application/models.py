"""Immutable public models for the AI-Clipper application facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.pipeline.models import PipelineProgress, PipelineRequest, PipelineResult


@dataclass(frozen=True, slots=True)
class ApplicationRequest:
    """Immutable input for one end-to-end AI-Clipper operation.

    Attributes:
        pipeline_request: Complete workflow configuration delegated to the pipeline.
    """

    pipeline_request: PipelineRequest


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    """Immutable successful outcome returned by the application facade.

    Attributes:
        pipeline_result: Complete result produced by the application pipeline.
    """

    pipeline_result: PipelineResult


@dataclass(frozen=True, slots=True)
class ApplicationProgress:
    """Immutable application-level wrapper for a pipeline progress event.

    Attributes:
        pipeline_progress: Normalized progress reported by the active pipeline.
    """

    pipeline_progress: PipelineProgress


ProgressCallback = Callable[[ApplicationProgress], None]
