"""Immutable application configuration with no environment dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import ProjectPaths


@dataclass(frozen=True, slots=True)
class ApplicationConfig:
    """Configuration shared by application modules.

    The configuration is immutable so a running workflow uses a consistent set
    of limits and locations. Environment loading is intentionally deferred to a
    later configuration module.
    """

    paths: ProjectPaths
    default_retries: int = 3
    default_download_quality: str = "best"
    maximum_filename_length: int = 180
    maximum_video_duration_seconds: int = 7_200
    maximum_file_size_bytes: int = 10 * 1_024 * 1_024 * 1_024

    def __post_init__(self) -> None:
        """Validate configuration limits at construction time."""
        if self.default_retries < 0:
            raise ValueError("default_retries must be zero or greater.")
        if not self.default_download_quality.strip():
            raise ValueError("default_download_quality must not be blank.")
        if self.maximum_filename_length < 1:
            raise ValueError("maximum_filename_length must be positive.")
        if self.maximum_video_duration_seconds < 1:
            raise ValueError("maximum_video_duration_seconds must be positive.")
        if self.maximum_file_size_bytes < 1:
            raise ValueError("maximum_file_size_bytes must be positive.")

    @classmethod
    def default(cls) -> ApplicationConfig:
        """Create the standard configuration for the current project layout."""
        return cls(paths=ProjectPaths.discover())

    @property
    def downloads_directory(self) -> Path:
        """Return the configured downloads directory."""
        return self.paths.downloads_directory

    @property
    def output_directory(self) -> Path:
        """Return the configured output directory."""
        return self.paths.output_directory

    @property
    def temp_directory(self) -> Path:
        """Return the configured temporary-files directory."""
        return self.paths.temp_directory

    @property
    def assets_directory(self) -> Path:
        """Return the configured assets directory."""
        return self.paths.assets_directory

    @property
    def logs_directory(self) -> Path:
        """Return the configured logs directory."""
        return self.paths.logs_directory
