"""Unit tests for the yt-dlp adapter with no network or media downloads."""

import logging
from pathlib import Path
from typing import Any

import pytest

from src.core.config import ApplicationConfig
from src.core.paths import ProjectPaths
from src.downloader.exceptions import DownloadFailedError, MetadataRetrievalError, VideoUnavailableError
from src.downloader.models import DownloadConfig, DownloadProgress, DownloadQuality, DownloadRequest, DownloadStatus
from src.downloader.service import VideoDownloader


class FakeYoutubeDL:
    """In-memory yt-dlp stand-in used to verify service orchestration."""

    response: dict[str, Any] = {}
    error: Exception | None = None
    instances: list["FakeYoutubeDL"] = []

    def __init__(self, options: dict[str, Any]) -> None:
        self.options = options
        type(self).instances.append(self)

    def __enter__(self) -> "FakeYoutubeDL":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def extract_info(self, _: str, *, download: bool) -> dict[str, Any]:
        """Return controlled metadata and synchronously emit fake progress."""
        if type(self).error is not None:
            raise type(self).error
        if download:
            for hook in self.options.get("progress_hooks", []):
                hook({"status": "downloading", "downloaded_bytes": 25, "total_bytes": 100})
                hook({"status": "finished"})
        return type(self).response

    def prepare_filename(self, info: dict[str, Any]) -> str:
        """Return the configured virtual yt-dlp output path."""
        return str(info["_filename"])


@pytest.fixture(autouse=True)
def replace_yt_dlp(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace yt-dlp before every test and reset the fake provider state."""
    FakeYoutubeDL.response = {}
    FakeYoutubeDL.error = None
    FakeYoutubeDL.instances = []
    monkeypatch.setattr("src.downloader.service.YoutubeDL", FakeYoutubeDL)


@pytest.fixture
def downloader(tmp_path: Path) -> VideoDownloader:
    """Build a service with test-local application paths and injected logging."""
    config = ApplicationConfig(paths=ProjectPaths(root=tmp_path))
    return VideoDownloader(config, logging.getLogger("tests.downloader"))


@pytest.fixture
def download_request(tmp_path: Path) -> DownloadRequest:
    """Build a valid request whose output directory is a pytest temporary path."""
    return DownloadRequest(
        source_url="https://www.youtube.com/watch?v=abc123",
        config=DownloadConfig(output_directory=tmp_path),
    )


def test_get_metadata_returns_typed_metadata(
    downloader: VideoDownloader, download_request: DownloadRequest
) -> None:
    """Metadata extraction is fully handled by the mocked yt-dlp adapter."""
    FakeYoutubeDL.response = _provider_info()
    metadata = downloader.get_metadata(download_request)
    assert metadata.video_id == "abc123"
    assert metadata.title == "Test Video"
    assert FakeYoutubeDL.instances[0].options["noplaylist"] is True


def test_get_metadata_translates_unavailable_provider_error(
    downloader: VideoDownloader, download_request: DownloadRequest
) -> None:
    """Provider errors never escape the service implementation boundary."""
    FakeYoutubeDL.error = RuntimeError("This video is private")
    with pytest.raises(VideoUnavailableError):
        downloader.get_metadata(download_request)


def test_get_metadata_translates_generic_provider_error(
    downloader: VideoDownloader, download_request: DownloadRequest
) -> None:
    """Unclassified provider failures become a downloader metadata error."""
    FakeYoutubeDL.error = RuntimeError("temporary provider failure")
    with pytest.raises(MetadataRetrievalError):
        downloader.get_metadata(download_request)


def test_download_video_returns_result_and_emits_progress(
    downloader: VideoDownloader, download_request: DownloadRequest, tmp_path: Path
) -> None:
    """A mocked completed provider response produces a stable result contract."""
    output_path = tmp_path / "Test_Video_abc123.mp4"
    output_path.touch()
    FakeYoutubeDL.response = _provider_info(output_path)
    progress_events: list[DownloadProgress] = []

    result = downloader.download_video(download_request, progress_events.append)

    assert result.local_path == output_path.resolve()
    assert result.metadata.video_id == "abc123"
    assert [event.status for event in progress_events] == [
        DownloadStatus.PREPARING,
        DownloadStatus.DOWNLOADING,
        DownloadStatus.PROCESSING,
        DownloadStatus.COMPLETED,
    ]


def test_download_video_translates_provider_error(
    downloader: VideoDownloader, download_request: DownloadRequest
) -> None:
    """Download failures are exposed as a domain exception, not yt-dlp errors."""
    FakeYoutubeDL.error = RuntimeError("network failure")
    with pytest.raises(DownloadFailedError):
        downloader.download_video(download_request)


@pytest.mark.parametrize(
    ("quality", "audio_only", "expected_format"),
    [
        (DownloadQuality.BEST, False, "best[ext=mp4]/best"),
        (DownloadQuality.MEDIUM, False, "best[height<=720][ext=mp4]/best[height<=720]/best"),
        (DownloadQuality.LOW, True, "bestaudio/best"),
    ],
)
def test_format_selection_uses_validated_preferences(
    quality: DownloadQuality, audio_only: bool, expected_format: str
) -> None:
    """Quality and audio-only settings map to explicit yt-dlp selectors."""
    assert VideoDownloader._select_format(quality, audio_only) == expected_format


def test_download_video_rejects_output_path_outside_configured_directory(
    downloader: VideoDownloader, download_request: DownloadRequest, tmp_path: Path
) -> None:
    """A provider-reported path cannot escape the configured output directory."""
    outside_path = tmp_path.parent / "outside.mp4"
    outside_path.touch()
    FakeYoutubeDL.response = _provider_info(outside_path)
    with pytest.raises(DownloadFailedError, match="outside the output directory"):
        downloader.download_video(download_request)


def _provider_info(output_path: Path | None = None) -> dict[str, Any]:
    """Return a representative yt-dlp response without any external I/O."""
    info: dict[str, Any] = {
        "id": "abc123",
        "title": "Test Video",
        "duration": 60,
        "channel": "Test Channel",
        "thumbnail": "https://img.example.test/thumb.jpg",
        "format_id": "18",
        "filesize": 1_000,
    }
    if output_path is not None:
        info["requested_downloads"] = [{"filepath": str(output_path)}]
        info["_filename"] = output_path
    return info
