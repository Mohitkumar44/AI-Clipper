"""Provider- and backend-independent exceptions for clip rendering."""


class ClipperError(Exception):
    """Base exception for expected clip-cutter failures."""


class InvalidClipRequestError(ClipperError):
    """Raised when a clip request contains invalid input or configuration."""


class ClipRenderingError(ClipperError):
    """Raised when a requested clip cannot be rendered successfully."""


class FFmpegNotFoundError(ClipperError):
    """Raised when the configured FFmpeg executable cannot be located."""


class InvalidTimestampError(ClipperError):
    """Raised when a clip timestamp range is invalid or unsafe to render."""


class OutputWriteError(ClipperError):
    """Raised when rendered clip output cannot be created or verified."""


class UnsupportedFormatError(ClipperError):
    """Raised when a requested output format is unsupported by the cutter."""


class ClipCancelledError(ClipperError):
    """Raised when a cancellable clip-rendering operation is cancelled."""
