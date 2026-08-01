"""Application exceptions for caption-data generation."""


class CaptionError(Exception):
    """Base exception for expected caption-module failures."""


class InvalidCaptionRequestError(CaptionError):
    """Raised when caption input or configuration is invalid."""


class CaptionGenerationError(CaptionError):
    """Raised when caption segmentation cannot complete successfully."""


class CaptionValidationError(CaptionError):
    """Raised when generated caption data violates application invariants."""
