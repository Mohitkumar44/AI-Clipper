"""Application service coordinating provider-neutral transcription work."""

from __future__ import annotations

import logging

from src.core.config import ApplicationConfig

from .backends.base import ProgressCallback, TranscriptionBackend
from .backends.factory import TranscriptionBackendFactory
from .exceptions import TranscriptError, TranscriptionFailedError
from .models import TranscriptRequest, TranscriptResult
from .validator import validate_transcript_request, validate_transcript_result


class TranscriptService:
    """Validate and delegate transcript requests to an injected backend factory."""

    def __init__(
        self,
        application_config: ApplicationConfig,
        logger: logging.Logger,
        backend_factory: TranscriptionBackendFactory,
    ) -> None:
        """Initialize the service with application-owned dependencies.

        Args:
            application_config: Shared immutable application configuration.
            logger: Structured application logger supplied by the composition root.
            backend_factory: Registry responsible for backend creation and defaults.
        """
        self._application_config = application_config
        self._logger = logger
        self._backend_factory = backend_factory

    def transcribe(
        self,
        request: TranscriptRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptResult:
        """Transcribe one local media request through the selected backend.

        Args:
            request: Immutable local-media transcription request.
            progress_callback: Optional receiver of backend-normalized progress.

        Returns:
            A validated, provider-independent transcript result.

        Raises:
            TranscriptError: If validation, backend selection, or transcription
                cannot complete successfully.
        """
        validate_transcript_request(request)
        backend = self._get_backend(request)
        self._logger.info(
            "transcript_service_started",
            extra={"event": "transcript_service_started", "backend": backend.backend_name()},
        )

        try:
            result = backend.transcribe(request, progress_callback)
            validate_transcript_result(result)
        except TranscriptError:
            raise
        except Exception:
            self._logger.exception(
                "transcript_service_failed",
                extra={"event": "transcript_service_failed", "backend": backend.backend_name()},
            )
            raise TranscriptionFailedError("The transcription backend failed unexpectedly.") from None

        self._logger.info(
            "transcript_service_completed",
            extra={
                "event": "transcript_service_completed",
                "backend": result.backend_name,
                "segment_count": len(result.segments),
            },
        )
        return result

    def _get_backend(self, request: TranscriptRequest) -> TranscriptionBackend:
        """Obtain the explicitly requested or configured default backend."""
        if request.backend_name is None:
            return self._backend_factory.get_default_backend()
        return self._backend_factory.get_backend(request.backend_name)
