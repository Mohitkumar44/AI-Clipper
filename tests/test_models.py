"""Tests for immutable downloader data models."""

from pathlib import Path

import pytest

from src.downloader.models import (
    DownloadConfig,
    DownloadProgress,
    DownloadQuality,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    VideoMetadata,
)


def test_download_config_is_immutable_and_preserves_settings(tmp_path: Path) -> None:
    """Download settings are frozen after successful construction."""
    config = DownloadConfig(
        output_directory=tmp_path,
        quality=DownloadQuality.MEDIUM,
        overwrite=True,
        retries=2,
        audio_only=True,
    )
    assert config.quality is DownloadQuality.MEDIUM
    assert config.audio_only is True
    with pytest.raises(AttributeError):
        config.retries = 1  # type: ignore[misc]


@pytest.mark.parametrize("kwargs", [{"retries": -1}, {"proxy_url": "ftp://proxy.local"}])
def test_download_config_rejects_invalid_constructor_values(tmp_path: Path, kwargs: dict[str, object]) -> None:
    """Model-level guards reject impossible configuration states."""
    with pytest.raises(ValueError):
        DownloadConfig(output_directory=tmp_path, **kwargs)  # type: ignore[arg-type]


def test_download_request_is_immutable_and_requires_youtube_url(tmp_path: Path) -> None:
    """Requests retain a typed immutable configuration and valid source URL."""
    request = DownloadRequest(
        source_url="https://www.youtube.com/watch?v=abc123",
        config=DownloadConfig(output_directory=tmp_path),
    )
    assert request.source_url.endswith("abc123")
    with pytest.raises(AttributeError):
        request.source_url = "https://youtube.com/watch?v=other"  # type: ignore[misc]


def test_download_request_rejects_non_youtube_url(tmp_path: Path) -> None:
    """The request model rejects unsupported source hosts at its boundary."""
    with pytest.raises(ValueError):
        DownloadRequest(
            source_url="https://example.com/video",
            config=DownloadConfig(output_directory=tmp_path),
        )


def test_download_result_carries_typed_metadata_and_output_path(tmp_path: Path) -> None:
    """A result provides future modules with one stable media handoff contract."""
    metadata = VideoMetadata(
        video_id="abc123",
        title="A video",
        duration_seconds=12.5,
        channel_name="Channel",
        source_url="https://www.youtube.com/watch?v=abc123",
        thumbnail_url=None,
    )
    result = DownloadResult(local_path=tmp_path / "clip.mp4", metadata=metadata, is_audio_only=False)
    assert result.local_path.suffix == ".mp4"
    assert result.metadata.video_id == "abc123"


def test_download_progress_calculates_percentage_safely() -> None:
    """Progress reports a bounded percentage only when a total is known."""
    assert DownloadProgress(DownloadStatus.DOWNLOADING, 50, 100).percentage == 50.0
    assert DownloadProgress(DownloadStatus.DOWNLOADING, 150, 100).percentage == 100.0
    assert DownloadProgress(DownloadStatus.DOWNLOADING, 50, None).percentage is None
