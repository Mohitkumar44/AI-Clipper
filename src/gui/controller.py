"""Controller coordinating threaded GUI generation with the application facade."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from src.application.models import ApplicationProgress, ApplicationRequest, ApplicationResult
from src.application.service import ApplicationService

from .exceptions import ApplicationExecutionError
from .worker import GenerationWorker


WorkerFactory = Callable[[ApplicationService, ApplicationRequest, logging.Logger], GenerationWorker]


class GenerationController(QObject):
    """Own worker lifecycle and relay its signals to the GUI without business logic."""

    progress_updated = Signal(object)
    generation_started = Signal()
    generation_completed = Signal(object)
    generation_failed = Signal(object)
    generation_cancelled = Signal()
    generation_finished = Signal()

    def __init__(
        self,
        application_service: ApplicationService,
        logger: logging.Logger,
        worker_factory: WorkerFactory = GenerationWorker,
    ) -> None:
        """Initialize controller collaborators through dependency injection.

        Args:
            application_service: Stable high-level application entry point.
            logger: Structured GUI logger.
            worker_factory: Factory used to create isolated background workers.
        """
        super().__init__()
        self._application_service = application_service
        self._logger = logger
        self._worker_factory = worker_factory
        self._thread: QThread | None = None
        self._worker: GenerationWorker | None = None

    @property
    def is_running(self) -> bool:
        """Return whether this controller currently owns a generation worker."""
        return self._thread is not None and self._thread.isRunning()

    def start_generation(self, request: ApplicationRequest) -> None:
        """Create and start a worker thread for one immutable application request.

        Args:
            request: Immutable request passed unchanged to ApplicationService.

        Raises:
            ApplicationExecutionError: If another generation is already active.
        """
        if self.is_running:
            raise ApplicationExecutionError("A generation job is already running.")
        thread = QThread(self)
        worker = self._worker_factory(self._application_service, request, self._logger)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress_updated.connect(self.progress_updated)
        worker.generation_completed.connect(self._on_completed)
        worker.generation_failed.connect(self._on_failed)
        worker.generation_cancelled.connect(self._on_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self._on_thread_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        self._worker = worker
        self._logger.info("gui_generation_thread_started", extra={"event": "gui_generation_thread_started"})
        self.generation_started.emit()
        thread.start()

    def request_cancellation(self) -> None:
        """Forward a basic cancellation request to the active worker if present."""
        if self._worker is None:
            return
        self._worker.request_cancellation()
        self._logger.info("gui_generation_cancellation_requested", extra={"event": "gui_generation_cancellation_requested"})

    def _on_completed(self, result: ApplicationResult) -> None:
        """Forward a successful immutable application result."""
        self.generation_completed.emit(result)

    def _on_failed(self, error: ApplicationExecutionError) -> None:
        """Forward a stable GUI error emitted by the worker."""
        self.generation_failed.emit(error)

    def _on_cancelled(self) -> None:
        """Forward terminal cancellation to presentation subscribers."""
        self.generation_cancelled.emit()

    def _on_thread_finished(self) -> None:
        """Release finished worker references and notify presentation subscribers."""
        self._logger.info("gui_generation_thread_finished", extra={"event": "gui_generation_thread_finished"})
        self._worker = None
        self._thread = None
        self.generation_finished.emit()
