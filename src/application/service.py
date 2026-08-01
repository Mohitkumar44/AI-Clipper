"""High-level application facade for the complete AI-Clipper workflow."""

from __future__ import annotations

import logging

from src.pipeline.exceptions import PipelineError
from src.pipeline.models import PipelineProgress
from src.pipeline.service import PipelineService

from .exceptions import ApplicationError, ApplicationPipelineError, InvalidApplicationRequestError
from .models import ApplicationProgress, ApplicationRequest, ApplicationResult, ProgressCallback


class ApplicationService:
    """Expose one stable entry point over an injected pipeline service."""

    def __init__(self, pipeline_service: PipelineService, logger: logging.Logger) -> None:
        """Initialize the facade with application-composition dependencies.

        Args:
            pipeline_service: Pipeline boundary responsible for the workflow.
            logger: Structured logger provided by the composition root.
        """
        self._pipeline_service = pipeline_service
        self._logger = logger

    def run(
        self,
        request: ApplicationRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> ApplicationResult:
        """Run a complete AI-Clipper workflow through the pipeline boundary.

        Args:
            request: Immutable request containing complete pipeline configuration.
            progress_callback: Optional receiver of application-level progress events.

        Returns:
            Immutable application result containing the completed pipeline result.

        Raises:
            ApplicationError: If the request is invalid or the pipeline fails.
        """
        if not isinstance(request, ApplicationRequest):
            raise InvalidApplicationRequestError("request must be an ApplicationRequest instance.")
        self._logger.info("application_run_started", extra={"event": "application_run_started"})
        try:
            result = self._pipeline_service.run(
                request.pipeline_request,
                lambda progress: self._forward_progress(progress_callback, progress),
            )
        except PipelineError as error:
            self._logger.exception("application_pipeline_failed", extra={"event": "application_pipeline_failed"})
            raise ApplicationPipelineError("The application pipeline failed.") from error
        except ApplicationError:
            raise
        except Exception as error:
            self._logger.exception("application_pipeline_failed", extra={"event": "application_pipeline_failed"})
            raise ApplicationPipelineError("The application pipeline failed unexpectedly.") from error
        self._logger.info("application_run_completed", extra={"event": "application_run_completed"})
        return ApplicationResult(result)

    def _forward_progress(
        self,
        callback: ProgressCallback | None,
        progress: PipelineProgress,
    ) -> None:
        """Forward one pipeline event without allowing callback failures to escape."""
        if callback is None:
            return
        try:
            callback(ApplicationProgress(progress))
        except Exception:
            self._logger.exception(
                "application_progress_callback_failed",
                extra={"event": "application_progress_callback_failed"},
            )
