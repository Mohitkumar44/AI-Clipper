"""Project-relative path definitions without filesystem side effects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Immutable collection of locations owned by the application.

    Constructing this model never creates directories. Creation belongs to the
    application bootstrap or to the narrowly scoped service that needs a path.
    """

    root: Path

    @classmethod
    def discover(cls) -> ProjectPaths:
        """Build paths from the repository layout containing this module."""
        return cls(root=Path(__file__).resolve().parents[2])

    @property
    def downloads_directory(self) -> Path:
        """Return the directory for downloaded source media."""
        return self.root / "downloads"

    @property
    def output_directory(self) -> Path:
        """Return the directory for rendered user-facing media."""
        return self.root / "output"

    @property
    def logs_directory(self) -> Path:
        """Return the directory for application log files."""
        return self.root / "logs"

    @property
    def temp_directory(self) -> Path:
        """Return the directory for disposable processing artifacts."""
        return self.root / "temp"

    @property
    def assets_directory(self) -> Path:
        """Return the directory for version-controlled application assets."""
        return self.root / "assets"


def project_root() -> Path:
    """Return the application project root."""
    return ProjectPaths.discover().root


def downloads() -> Path:
    """Return the downloads directory without creating it."""
    return ProjectPaths.discover().downloads_directory


def output() -> Path:
    """Return the output directory without creating it."""
    return ProjectPaths.discover().output_directory


def logs() -> Path:
    """Return the logs directory without creating it."""
    return ProjectPaths.discover().logs_directory


def temp() -> Path:
    """Return the temporary-files directory without creating it."""
    return ProjectPaths.discover().temp_directory


def assets() -> Path:
    """Return the application-assets directory without creating it."""
    return ProjectPaths.discover().assets_directory
