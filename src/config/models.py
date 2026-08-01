"""Immutable models for application-level user preferences and credentials."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Theme(str, Enum):
    """Supported desktop appearance preferences."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    """Immutable in-memory configuration available to the composition root.

    Attributes:
        openai_api_key: Optional API key supplied by a future secure settings source.
        gemini_api_key: Optional API key supplied by a future secure settings source.
        default_output_directory: Application-controlled default output location.
        preferred_analyzer_provider: Provider identifier preferred for analysis.
        preferred_transcript_backend: Backend identifier preferred for transcription.
        theme: Requested desktop appearance.
    """

    openai_api_key: str | None
    gemini_api_key: str | None
    default_output_directory: Path
    preferred_analyzer_provider: str
    preferred_transcript_backend: str
    theme: Theme
