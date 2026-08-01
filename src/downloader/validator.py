"""Pure validation and normalization utilities for downloader inputs."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from .exceptions import DownloaderError, InvalidVideoUrlError
from .models import DownloadConfig, DownloadQuality, SUPPORTED_YOUTUBE_HOSTS


LOGGER = logging.getLogger(__name__)
CANONICAL_YOUTUBE_HOST: Final[str] = "www.youtube.com"
YOUTUBE_SHORT_HOST: Final[str] = "youtu.be"
ALLOWED_PROXY_SCHEMES: Final[frozenset[str]] = frozenset(
    {"http", "https", "socks4", "socks5"}
)
WINDOWS_RESERVED_FILENAMES: Final[frozenset[str]] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    }
)
INVALID_FILENAME_CHARACTERS: Final[frozenset[str]] = frozenset('<>:"/\\|?*')


class InvalidDownloadConfigurationError(DownloaderError):
    """Raised when downloader configuration is invalid or unsafe."""


class UnsafeFilenameError(DownloaderError):
    """Raised when a filename is invalid or unsafe for Windows storage."""


def normalize_youtube_url(url: str) -> str:
    """Validate and normalize a YouTube video URL to a stable canonical form.

    Shortened ``youtu.be`` links are converted to standard watch URLs. Tracking
    query parameters are discarded; a playlist parameter is retained when one
    is present for a future playlist module.

    Args:
        url: The untrusted URL supplied by a caller.

    Returns:
        A normalized HTTPS YouTube URL.

    Raises:
        InvalidVideoUrlError: If the URL is blank, unsupported, or lacks a
            recognizable video identifier.
    """
    if not isinstance(url, str) or not url.strip():
        raise InvalidVideoUrlError("A YouTube URL is required.")

    parsed_url = urlparse(url.strip())
    host = (parsed_url.hostname or "").lower()
    if parsed_url.scheme.lower() not in {"http", "https"}:
        raise InvalidVideoUrlError("The YouTube URL must use HTTP or HTTPS.")
    if host not in SUPPORTED_YOUTUBE_HOSTS:
        raise InvalidVideoUrlError("The URL does not use a supported YouTube host.")

    video_id = _extract_video_id(parsed_url, host)
    if not video_id:
        raise InvalidVideoUrlError("The YouTube URL does not identify a video.")

    query_values = parse_qs(parsed_url.query, keep_blank_values=False)
    query_parameters = {"v": video_id}
    if "list" in query_values:
        query_parameters["list"] = query_values["list"][0]

    normalized_url = urlunparse(
        (
            "https",
            CANONICAL_YOUTUBE_HOST,
            "/watch",
            "",
            urlencode(query_parameters),
            "",
        )
    )
    LOGGER.debug("Normalized a YouTube source URL.")
    return normalized_url


def validate_proxy_url(proxy_url: str | None) -> str | None:
    """Validate a configured proxy URL without logging its credentials.

    Args:
        proxy_url: An optional HTTP(S) or SOCKS proxy URL.

    Returns:
        The stripped proxy URL, or ``None`` when no proxy is configured.

    Raises:
        InvalidDownloadConfigurationError: If the URL has an unsupported scheme
            or does not include a host.
    """
    if proxy_url is None:
        return None
    if not isinstance(proxy_url, str) or not proxy_url.strip():
        raise InvalidDownloadConfigurationError("proxy_url must be a non-empty URL.")

    normalized_proxy_url = proxy_url.strip()
    parsed_url = urlparse(normalized_proxy_url)
    if parsed_url.scheme.lower() not in ALLOWED_PROXY_SCHEMES:
        raise InvalidDownloadConfigurationError(
            "proxy_url must use HTTP(S), SOCKS4, or SOCKS5."
        )
    if not parsed_url.hostname:
        raise InvalidDownloadConfigurationError("proxy_url must include a host.")
    return normalized_proxy_url


def validate_output_directory(output_directory: Path) -> Path:
    """Validate an existing directory suitable for downloader output.

    This function performs read-only checks only; directory creation belongs to
    application setup or the download service.

    Raises:
        InvalidDownloadConfigurationError: If the value is not an existing
            directory.
    """
    if not isinstance(output_directory, Path):
        raise InvalidDownloadConfigurationError("output_directory must be a Path.")

    expanded_directory = output_directory.expanduser()
    if not expanded_directory.exists() or not expanded_directory.is_dir():
        raise InvalidDownloadConfigurationError(
            "output_directory must be an existing directory."
        )
    return expanded_directory


def validate_download_quality(quality: DownloadQuality) -> DownloadQuality:
    """Validate a high-level download quality preference.

    Raises:
        InvalidDownloadConfigurationError: If *quality* is not a supported enum
            value.
    """
    if not isinstance(quality, DownloadQuality):
        raise InvalidDownloadConfigurationError("quality must be a DownloadQuality value.")
    return quality


def validate_download_config(config: DownloadConfig) -> DownloadConfig:
    """Validate all downloader settings without changing the immutable config.

    Raises:
        InvalidDownloadConfigurationError: If the configuration or a configured
            file path is invalid.
    """
    if not isinstance(config, DownloadConfig):
        raise InvalidDownloadConfigurationError("config must be a DownloadConfig instance.")

    validate_output_directory(config.output_directory)
    validate_download_quality(config.quality)
    validate_proxy_url(config.proxy_url)

    if config.retries < 0:
        raise InvalidDownloadConfigurationError("retries must be zero or greater.")
    if config.cookies_path is not None:
        cookies_path = config.cookies_path.expanduser()
        if not cookies_path.is_file():
            raise InvalidDownloadConfigurationError(
                "cookies_path must reference an existing file."
            )
    return config


def validate_filename_safety(filename: str) -> str:
    """Validate a filename for safe use in the Windows downloads directory.

    This validates a filename only, not a full path. Callers must still combine
    it with an application-controlled output directory.

    Raises:
        UnsafeFilenameError: If the name is empty, contains unsafe characters,
            or is a reserved Windows device name.
    """
    if not isinstance(filename, str) or not filename.strip():
        raise UnsafeFilenameError("filename must be a non-empty string.")

    candidate = filename.strip()
    if Path(candidate).name != candidate:
        raise UnsafeFilenameError("filename must not include path components.")
    if any(character in INVALID_FILENAME_CHARACTERS for character in candidate):
        raise UnsafeFilenameError("filename contains characters unsupported by Windows.")
    if candidate.endswith((".", " ")):
        raise UnsafeFilenameError("filename must not end with a period or space.")
    if candidate.split(".", maxsplit=1)[0].lower() in WINDOWS_RESERVED_FILENAMES:
        raise UnsafeFilenameError("filename uses a reserved Windows device name.")
    return candidate


def _extract_video_id(parsed_url: object, host: str) -> str | None:
    """Extract a video identifier from a parsed, previously validated URL."""
    path = getattr(parsed_url, "path", "").strip("/")
    query = parse_qs(getattr(parsed_url, "query", ""), keep_blank_values=False)
    if host in {YOUTUBE_SHORT_HOST, f"www.{YOUTUBE_SHORT_HOST}"}:
        return path.split("/", maxsplit=1)[0] or None
    if path == "watch":
        return query.get("v", [None])[0]
    if path.startswith(("shorts/", "embed/", "live/")):
        return path.split("/", maxsplit=1)[1] or None
    return None
