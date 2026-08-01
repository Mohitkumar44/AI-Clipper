"""yt-dlp-backed service for downloading a single YouTube video."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from src.core.config import ApplicationConfig

from .exceptions import (
    DownloadFailedError,
    DownloaderError,
    MetadataRetrievalError,
    VideoUnavailableError,
)
from .models import (
    DownloadConfig,
    DownloadProgress,
    DownloadQuality,
    DownloadRequest,
    DownloadResult,
    DownloadStatus,
    VideoMetadata,
)
from .validator import (
    normalize_youtube_url,
    validate_download_config,
    validate_filename_safety,
)


ProgressCallback = Callable[[DownloadProgress], None]


class VideoDownloader:
    """Download one validated YouTube video using the yt-dlp Python API."""

    def __init__(self, application_config: ApplicationConfig, logger: logging.Logger) -> None:
        """Initialize the service with immutable application configuration.

        Args:
            application_config: Shared configuration containing global limits.
            logger: Application logger supplied by the composition root.
        """
        self._application_config = application_config
        self._logger = logger

    def get_metadata(self, request: DownloadRequest) -> VideoMetadata:
        """Retrieve source metadata without downloading media.

        Raises:
            DownloaderError: If request validation or metadata retrieval fails.
        """
        normalized_url, config = self._validate_request(request)
        self._logger.info("metadata_retrieval_started", extra={"event": "metadata_retrieval"})

        try:
            with YoutubeDL(self._build_yt_dlp_options(config)) as downloader:
                info = downloader.extract_info(normalized_url, download=False)
        except DownloaderError:
            raise
        except Exception as error:
            self._logger.exception(
                "metadata_retrieval_failed", extra={"event": "metadata_retrieval_failed"}
            )
            raise self._translate_provider_error(error, MetadataRetrievalError) from None

        metadata = self._build_metadata(info, normalized_url)
        self._validate_media_limits(info, metadata)
        self._logger.info("metadata_retrieval_completed", extra={"event": "metadata_retrieval"})
        return metadata

    def download_video(
        self,
        request: DownloadRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> DownloadResult:
        """Download one video and return its local path and source metadata.

        Raises:
            DownloaderError: If validation fails or yt-dlp cannot download media.
        """
        normalized_url, config = self._validate_request(request)
        self._emit_progress(progress_callback, DownloadProgress(status=DownloadStatus.PREPARING))
        self._logger.info("video_download_started", extra={"event": "video_download"})

        try:
            options = self._build_yt_dlp_options(
                config,
                progress_callback=progress_callback,
            )
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(normalized_url, download=True)
                result = self._build_download_result(downloader, info, normalized_url, config)
        except DownloaderError:
            raise
        except Exception as error:
            self._logger.exception("video_download_failed", extra={"event": "video_download_failed"})
            raise self._translate_provider_error(error, DownloadFailedError) from None

        self._emit_progress(progress_callback, DownloadProgress(status=DownloadStatus.COMPLETED))
        self._logger.info(
            "video_download_completed",
            extra={"event": "video_download", "video_id": result.metadata.video_id},
        )
        return result

    def _validate_request(self, request: DownloadRequest) -> tuple[str, DownloadConfig]:
        """Validate a request through the dedicated validator module."""
        if not isinstance(request, DownloadRequest):
            raise DownloadFailedError("request must be a DownloadRequest instance.")

        normalized_url = normalize_youtube_url(request.source_url)
        config = validate_download_config(request.config)
        return normalized_url, config

    def _build_yt_dlp_options(
        self,
        config: DownloadConfig,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Build yt-dlp options without invoking external commands or FFmpeg."""
        options: dict[str, Any] = {
            "format": self._select_format(config.quality, config.audio_only),
            "outtmpl": str(config.output_directory / "%(title)s [%(id)s].%(ext)s"),
            "trim_file_name": self._application_config.maximum_filename_length,
            "noplaylist": True,
            "overwrites": config.overwrite,
            "retries": config.retries,
            "restrictfilenames": True,
            "quiet": True,
            "noprogress": True,
        }
        if config.cookies_path is not None:
            options["cookiefile"] = str(config.cookies_path)
        if config.proxy_url is not None:
            options["proxy"] = config.proxy_url
        if progress_callback is not None:
            options["progress_hooks"] = [self._create_progress_hook(progress_callback)]
        return options

    def _create_progress_hook(self, callback: ProgressCallback) -> Callable[[dict[str, Any]], None]:
        """Create a yt-dlp hook that emits normalized progress data."""
        def progress_hook(status: dict[str, Any]) -> None:
            provider_status = status.get("status")
            if provider_status == "downloading":
                progress = DownloadProgress(
                    status=DownloadStatus.DOWNLOADING,
                    downloaded_bytes=_as_optional_int(status.get("downloaded_bytes")),
                    total_bytes=_as_optional_int(
                        status.get("total_bytes") or status.get("total_bytes_estimate")
                    ),
                )
            elif provider_status == "finished":
                progress = DownloadProgress(status=DownloadStatus.PROCESSING)
            else:
                return
            self._emit_progress(callback, progress)

        return progress_hook

    def _build_download_result(
        self,
        downloader: YoutubeDL,
        info: dict[str, Any],
        source_url: str,
        config: DownloadConfig,
    ) -> DownloadResult:
        """Build a typed result and verify the produced media path is safe."""
        metadata = self._build_metadata(info, source_url)
        self._validate_media_limits(info, metadata)
        output_path = self._resolve_output_path(downloader, info)
        validate_filename_safety(output_path.name)
        if len(output_path.name) > self._application_config.maximum_filename_length:
            raise DownloadFailedError("The downloaded filename exceeds the configured limit.")

        try:
            output_path.relative_to(config.output_directory.expanduser().resolve())
        except ValueError as error:
            raise DownloadFailedError("The downloaded file is outside the output directory.") from error
        if not output_path.is_file():
            raise DownloadFailedError("yt-dlp completed without producing an output file.")

        return DownloadResult(
            local_path=output_path,
            metadata=metadata,
            is_audio_only=config.audio_only,
            format_id=_as_optional_str(info.get("format_id")),
        )

    def _build_metadata(self, info: Any, source_url: str) -> VideoMetadata:
        """Convert untrusted yt-dlp metadata into the public metadata model."""
        if not isinstance(info, dict):
            raise MetadataRetrievalError("yt-dlp did not return video metadata.")

        video_id = _as_optional_str(info.get("id"))
        title = _as_optional_str(info.get("title"))
        if video_id is None or title is None:
            raise MetadataRetrievalError("The source video is missing required metadata.")

        duration = info.get("duration")
        return VideoMetadata(
            video_id=video_id,
            title=title,
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
            channel_name=_as_optional_str(info.get("channel") or info.get("uploader")),
            source_url=source_url,
            thumbnail_url=_as_optional_str(info.get("thumbnail")),
        )

    def _validate_media_limits(self, info: dict[str, Any], metadata: VideoMetadata) -> None:
        """Enforce shared size and duration limits before accepting media."""
        duration = metadata.duration_seconds
        if duration is not None and duration > self._application_config.maximum_video_duration_seconds:
            raise DownloadFailedError("The video exceeds the configured duration limit.")

        file_size = _as_optional_int(info.get("filesize") or info.get("filesize_approx"))
        if file_size is not None and file_size > self._application_config.maximum_file_size_bytes:
            raise DownloadFailedError("The video exceeds the configured file size limit.")

    def _resolve_output_path(self, downloader: YoutubeDL, info: dict[str, Any]) -> Path:
        """Resolve the completed media path reported by yt-dlp."""
        requested_downloads = info.get("requested_downloads")
        if isinstance(requested_downloads, list) and requested_downloads:
            file_path = requested_downloads[0].get("filepath")
            if isinstance(file_path, str):
                return Path(file_path).resolve()
        return Path(downloader.prepare_filename(info)).resolve()

    def _emit_progress(self, callback: ProgressCallback | None, progress: DownloadProgress) -> None:
        """Invoke a caller progress callback without allowing it to break download work."""
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            self._logger.exception("progress_callback_failed", extra={"event": "progress_callback"})

    @staticmethod
    def _select_format(quality: DownloadQuality, audio_only: bool) -> str:
        """Map validated quality preferences to yt-dlp format selectors."""
        if audio_only:
            return "bestaudio/best"
        formats = {
            DownloadQuality.BEST: "best[ext=mp4]/best",
            DownloadQuality.HIGH: "best[height<=1080][ext=mp4]/best[height<=1080]/best",
            DownloadQuality.MEDIUM: "best[height<=720][ext=mp4]/best[height<=720]/best",
            DownloadQuality.LOW: "best[height<=480][ext=mp4]/best[height<=480]/best",
        }
        return formats[quality]

    @staticmethod
    def _translate_provider_error(
        error: Exception,
        default_exception: type[DownloaderError],
    ) -> DownloaderError:
        """Map provider messages to stable public downloader exceptions."""
        message = str(error).lower()
        if any(keyword in message for keyword in ("private", "unavailable", "removed", "restricted")):
            return VideoUnavailableError("The requested video is unavailable.")
        return default_exception("yt-dlp could not complete the requested operation.")


def _as_optional_int(value: Any) -> int | None:
    """Return an integer value when *value* is an integer but not a boolean."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _as_optional_str(value: Any) -> str | None:
    """Return a non-blank string value, otherwise ``None``."""
    return value.strip() if isinstance(value, str) and value.strip() else None
