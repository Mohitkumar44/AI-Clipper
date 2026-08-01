"""Background worker for long-running application generation requests."""

from __future__ import annotations

import logging
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from src.application.exceptions import ApplicationError
from src.application.models import ApplicationProgress, ApplicationRequest, ApplicationResult
from src.application.service import ApplicationService

from .exceptions import ApplicationExecutionError


class GenerationWorker(QObject):
    """Run one application request outside the GUI thread.

    Cancellation is deliberately cooperative: it cannot interrupt an active
    application operation, but prevents further progress and successful-result
    delivery after the operation returns.
    """

    progress_updated = Signal(object)
    generation_completed = Signal(object)
    generation_failed = Signal(object)
    generation_cancelled = Signal()
    finished = Signal()

    def __init__(
        self,
        application_service: ApplicationService,
        request: ApplicationRequest,
        logger: logging.Logger,
    ) -> None:
        """Initialize one background operation using injected dependencies.

        Args:
            application_service: High-level application entry point.
            request: Immutable application request to execute.
            logger: Structured application logger.
        """
        super().__init__()
        self._application_service = application_service
        self._request = request
        self._logger = logger
        self._cancel_requested = Event()

    @Slot()
    def run(self) -> None:
        """Execute the application request and emit a terminal lifecycle signal."""
        if self._cancel_requested.is_set():
            self._logger.info("gui_worker_cancelled_before_start", extra={"event": "gui_worker_cancelled"})
            self.generation_cancelled.emit()
            self.finished.emit()
            return
        try:
            result = self._application_service.run(self._request, self._handle_progress)
        except ApplicationError as error:
            self._emit_failure(error)
        except Exception as error:
            self._emit_failure(error)
        else:
            if self._cancel_requested.is_set():
                self._logger.info("gui_worker_cancelled_after_run", extra={"event": "gui_worker_cancelled"})
                self.generation_cancelled.emit()
            else:
                self._logger.info("gui_worker_completed", extra={"event": "gui_worker_completed"})
                self.generation_completed.emit(result)
        finally:
            self.finished.emit()

    @Slot()
    def request_cancellation(self) -> None:
        """Record a basic cancellation request without interrupting backend work."""
        self._cancel_requested.set()
        self._logger.info("gui_worker_cancellation_requested", extra={"event": "gui_worker_cancellation_requested"})

    def _handle_progress(self, progress: ApplicationProgress) -> None:
        """Forward application progress unless cancellation has been requested."""
        if not self._cancel_requested.is_set():
            self.progress_updated.emit(progress)

    def _emit_failure(self, error: Exception) -> None:
        """Translate any application-facing failure into a stable GUI exception."""
        self._logger.exception("gui_worker_failed", extra={"event": "gui_worker_failed"})
        failure = ApplicationExecutionError("Generation could not be completed.")
        self.generation_failed.emit(failure)
