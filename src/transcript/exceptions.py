"""Application-level exceptions for the transcript domain."""


class TranscriptError(Exception):
    """Base exception for expected transcript-module failures."""


class InvalidTranscriptRequestError(TranscriptError):
    """Raised when a transcription request contains invalid settings or input."""


class MediaFileNotFoundError(TranscriptError):
    """Raised when the requested local media file does not exist."""


class MediaFormatNotSupportedError(TranscriptError):
    """Raised when the selected backend cannot read the supplied media format."""


class UnsupportedLanguageError(TranscriptError):
    """Raised when a requested language is unsupported by the selected backend."""


class AudioExtractionError(TranscriptError):
    """Raised when audio cannot be read or prepared from the input media."""


class ModelLoadError(TranscriptError):
    """Raised when a transcription model cannot be initialized."""


class ModelNotAvailableError(TranscriptError):
    """Raised when a required transcription model is unavailable locally."""


class TranscriptionFailedError(TranscriptError):
    """Raised when transcription cannot complete successfully."""


class TranscriptValidationError(TranscriptError):
    """Raised when backend transcript data violates application invariants."""


class TranscriptionCancelledError(TranscriptError):
    """Raised when a cancellable transcription operation is cancelled."""
