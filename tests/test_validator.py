"""Tests for pure downloader input validation."""

from pathlib import Path

import pytest

from src.downloader.exceptions import InvalidVideoUrlError
from src.downloader.models import DownloadConfig, DownloadQuality
from src.downloader.validator import (
    InvalidDownloadConfigurationError,
    UnsafeFilenameError,
    normalize_youtube_url,
    validate_download_config,
    validate_download_quality,
    validate_filename_safety,
    validate_output_directory,
    validate_proxy_url,
)


@pytest.mark.parametrize(
    ("source_url", "expected"),
    [
        ("https://youtu.be/abc123?t=5", "https://www.youtube.com/watch?v=abc123"),
        ("https://www.youtube.com/shorts/abc123", "https://www.youtube.com/watch?v=abc123"),
        ("https://youtube.com/watch?v=abc123&list=playlist1", "https://www.youtube.com/watch?v=abc123&list=playlist1"),
    ],
)
def test_normalize_youtube_url_returns_canonical_video_url(source_url: str, expected: str) -> None:
    """Supported YouTube URL forms normalize to one predictable shape."""
    assert normalize_youtube_url(source_url) == expected


@pytest.mark.parametrize(
    "source_url",
    ["", "ftp://youtube.com/watch?v=abc", "https://example.com/watch?v=abc", "https://youtube.com/"],
)
def test_normalize_youtube_url_rejects_invalid_urls(source_url: str) -> None:
    """Unsupported and incomplete URLs produce the domain-specific exception."""
    with pytest.raises(InvalidVideoUrlError):
        normalize_youtube_url(source_url)


def test_validate_proxy_url_accepts_supported_proxy() -> None:
    """HTTP and SOCKS proxy schemes are accepted as opaque configuration."""
    proxy = "socks5://user:secret@localhost:1080"
    assert validate_proxy_url(proxy) == proxy


@pytest.mark.parametrize("proxy_url", ["localhost:8080", "ftp://localhost", "https://"])
def test_validate_proxy_url_rejects_invalid_proxy(proxy_url: str) -> None:
    """Malformed proxy values use a downloader configuration error."""
    with pytest.raises(InvalidDownloadConfigurationError):
        validate_proxy_url(proxy_url)


def test_validate_output_directory_returns_existing_directory(tmp_path: Path) -> None:
    """Existing directories are preserved as pathlib paths."""
    assert validate_output_directory(tmp_path) == tmp_path


def test_validate_output_directory_rejects_missing_directory(tmp_path: Path) -> None:
    """The validator does not create missing output directories."""
    with pytest.raises(InvalidDownloadConfigurationError):
        validate_output_directory(tmp_path / "missing")


def test_validate_download_config_accepts_complete_valid_config(tmp_path: Path) -> None:
    """A valid immutable configuration remains unchanged after validation."""
    config = DownloadConfig(output_directory=tmp_path, quality=DownloadQuality.HIGH)
    assert validate_download_config(config) is config


def test_validate_download_quality_rejects_non_enum_value() -> None:
    """Quality values must use the model's explicit enum."""
    with pytest.raises(InvalidDownloadConfigurationError):
        validate_download_quality("best")  # type: ignore[arg-type]


@pytest.mark.parametrize("filename", ["clip.mp4", "short_01.webm", "A title [abc123].mp4"])
def test_validate_filename_safety_accepts_safe_names(filename: str) -> None:
    """Ordinary generated media filenames are accepted."""
    assert validate_filename_safety(filename) == filename


@pytest.mark.parametrize("filename", ["", "../clip.mp4", "bad:name.mp4", "CON.mp4", "clip. "])
def test_validate_filename_safety_rejects_unsafe_names(filename: str) -> None:
    """Unsafe and Windows-reserved filenames are rejected."""
    with pytest.raises(UnsafeFilenameError):
        validate_filename_safety(filename)
