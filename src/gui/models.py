"""Immutable presentation models for the AI-Clipper desktop interface."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class GenerationStatus(str, Enum):
    """Display states for the generation workflow."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class GenerationFormData:
    """Immutable values collected from the generation form.

    Attributes:
        source_url: User-supplied YouTube URL.
        output_directory: User-selected destination for generated clips.
    """

    source_url: str
    output_directory: Path


@dataclass(frozen=True, slots=True)
class GenerationViewState:
    """Immutable state required to render generation progress in the window.

    Attributes:
        status: Current presentation status.
        progress_percentage: Normalized progress value from zero to one hundred.
        message: Short safe status text for the user.
    """

    status: GenerationStatus
    progress_percentage: int
    message: str
