"""Provider-independent exceptions for transcript analysis."""


class AnalyzerError(Exception):
    """Base exception for expected analyzer-module failures."""


class InvalidAnalysisRequestError(AnalyzerError):
    """Raised when an analysis request contains invalid input or settings."""


class UnsupportedAnalyzerError(AnalyzerError):
    """Raised when a requested analyzer implementation is unavailable."""


class AnalysisFailedError(AnalyzerError):
    """Raised when analysis cannot complete successfully."""


class ProviderCommunicationError(AnalyzerError):
    """Raised when an analyzer provider cannot be reached or respond safely."""


class InvalidAnalysisResultError(AnalyzerError):
    """Raised when provider output violates application result invariants."""


class RateLimitExceededError(AnalyzerError):
    """Raised when an analyzer provider rejects a request due to rate limits."""


class AnalyzerConfigurationError(AnalyzerError):
    """Raised when analyzer setup is incomplete, invalid, or incompatible."""
