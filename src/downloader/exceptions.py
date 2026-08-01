"""Download-domain exceptions.

The concrete shared exception base will live in ``src.core.exceptions`` when
the core package is added. These exceptions remain specific to downloader
failures so callers never need to handle yt-dlp implementation details.
"""


class DownloaderError(Exception):
    """Base exception for expected downloader failures."""


class InvalidVideoUrlError(DownloaderError):
    """Raised when a source URL is invalid or unsupported."""


class MetadataRetrievalError(DownloaderError):
    """Raised when metadata cannot be retrieved from the source video."""


class VideoUnavailableError(DownloaderError):
    """Raised when a video is private, removed, restricted, or unavailable."""


class DownloadFailedError(DownloaderError):
    """Raised when a video download cannot complete successfully."""


class DownloadCancelledError(DownloaderError):
    """Raised when a future cancellable download operation is cancelled."""
