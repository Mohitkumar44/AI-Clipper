"""Application exceptions for complete workflow orchestration."""


class PipelineError(Exception):
    """Base exception for expected pipeline orchestration failures."""


class InvalidPipelineRequestError(PipelineError):
    """Raised when a pipeline request contains invalid stage configuration."""


class DownloadStageError(PipelineError):
    """Raised when the downloader stage cannot complete safely."""


class TranscriptStageError(PipelineError):
    """Raised when the transcript stage cannot complete safely."""


class AnalysisStageError(PipelineError):
    """Raised when the analyzer stage cannot complete safely."""


class ClipRenderingStageError(PipelineError):
    """Raised when the clip-rendering stage cannot complete safely."""
