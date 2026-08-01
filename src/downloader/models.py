"""Immutable data models for the video download domain.

These models define the boundary between callers and the downloader service.
They intentionally contain no yt-dlp, FFmpeg, GUI, or filesystem side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Final
from urllib.parse import urlparse


DEFAULT_QUALITY: Final[str] = "best"
DEFAULT_RETRIES: Final[int] = 3
SUPPORTED_YOUTUBE_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "www.youtu.be",
    }
)


class DownloadQuality(str, Enum):
    """Supported high-level video quality preferences."""

    BEST = "best"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DownloadStatus(str, Enum):
    """States reported while a download is running."""

    PREPARING = "preparing"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class DownloadConfig:
    """Settings controlling one or more video download operations.

    Attributes:
        output_directory: Directory in which the service stores downloaded media.
        quality: High-level preference translated to a yt-dlp format by the service.
        overwrite: Whether an existing matching output may be replaced.
        retries: Number of retry attempts for transient download failures.
        cookies_path: Optional Netscape-format cookies file for authorized access.
        proxy_url: Optional HTTP(S) or SOCKS proxy URL.
        audio_only: Whether to request audio without a video stream.
    """

    output_directory: Path
    quality: DownloadQuality = DownloadQuality.BEST
    overwrite: bool = False
    retries: int = DEFAULT_RETRIES
    cookies_path: Path | None = None
    proxy_url: str | None = None
    audio_only: bool = False

    def __post_init__(self) -> None:
        """Validate values without creating directories or reading external files."""
        if not self.output_directory.name:
            raise ValueError("output_directory must identify a directory.")
        if self.retries < 0:
            raise ValueError("retries must be zero or greater.")
        if self.proxy_url is not None:
            _validate_proxy_url(self.proxy_url)


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    """A validated request to download one YouTube video."""

    source_url: str
    config: DownloadConfig

    def __post_init__(self) -> None:
        """Reject empty or unsupported source URLs at the module boundary."""
        _validate_youtube_url(self.source_url)


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Source metadata made available by the download provider."""

    video_id: str
    title: str
    duration_seconds: float | None
    channel_name: str | None
    source_url: str
    thumbnail_url: str | None


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    """An immutable progress event emitted by the downloader service."""

    status: DownloadStatus
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    message: str | None = None

    @property
    def percentage(self) -> float | None:
        """Return progress as a percentage when a total size is available."""
        if self.total_bytes is None or self.total_bytes <= 0:
            return None
        if self.downloaded_bytes is None:
            return 0.0
        return min(100.0, (self.downloaded_bytes / self.total_bytes) * 100)


@dataclass(frozen=True, slots=True)
class DownloadResult:
    """Successful downloader output consumed by subsequent application modules."""

    local_path: Path
    metadata: VideoMetadata
    is_audio_only: bool
    format_id: str | None = None


def _validate_youtube_url(url: str) -> None:
    """Validate that *url* is a well-formed URL for a supported YouTube host."""
    parsed_url = urlparse(url.strip())
    if parsed_url.scheme not in {"http", "https"}:
        raise ValueError("source_url must use HTTP or HTTPS.")
    if parsed_url.hostname not in SUPPORTED_YOUTUBE_HOSTS:
        raise ValueError("source_url must use a supported YouTube host.")


def _validate_proxy_url(proxy_url: str) -> None:
    """Validate the shape of a proxy URL without exposing credentials."""
    parsed_url = urlparse(proxy_url)
    if parsed_url.scheme not in {"http", "https", "socks4", "socks5"}:
        raise ValueError("proxy_url must use HTTP(S), SOCKS4, or SOCKS5.")
    if not parsed_url.hostname:
        raise ValueError("proxy_url must include a host.")
