"""Main PySide6 window containing only AI-Clipper presentation logic."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.application.models import ApplicationProgress, ApplicationRequest

from .controller import GenerationController
from .dialogs.settings_dialog import SettingsDialog
from .exceptions import ApplicationExecutionError, GuiError
from .models import GenerationFormData, GenerationStatus, GenerationViewState


RequestFactory = Callable[[GenerationFormData], ApplicationRequest]
SettingsDialogFactory = Callable[[QWidget], SettingsDialog]


class DialogPresenter(Protocol):
    """Abstract user-dialog boundary used by the main window."""

    def show_error(self, parent: QWidget, title: str, message: str) -> None:
        """Display one safe error dialog."""

    def confirm_close(self, parent: QWidget) -> bool:
        """Return whether the user wants to cancel active work and close later."""


class QtDialogPresenter:
    """PySide6 implementation of safe modal dialog presentation."""

    def show_error(self, parent: QWidget, title: str, message: str) -> None:
        """Display an error without exposing a traceback to the user."""
        QMessageBox.critical(parent, title, message)

    def confirm_close(self, parent: QWidget) -> bool:
        """Ask whether the active generation should receive a cancel request."""
        response = QMessageBox.question(
            parent,
            "Generation in progress",
            "Generation is still running. Request cancellation and close when it finishes?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return response is QMessageBox.StandardButton.Yes


class MainWindow(QMainWindow):
    """Provide non-blocking generation controls for the AI-Clipper desktop app."""

    generation_requested = Signal(object)

    def __init__(
        self,
        controller: GenerationController,
        request_factory: RequestFactory,
        dialog_presenter: DialogPresenter | None = None,
        settings_dialog_factory: SettingsDialogFactory = SettingsDialog,
    ) -> None:
        """Build the window from injected presentation collaborators.

        Args:
            controller: Thread-owning controller connected to ApplicationService.
            request_factory: Composition-layer adapter that creates application requests.
            dialog_presenter: Optional safe dialog implementation.
            settings_dialog_factory: Factory for the placeholder settings dialog.
        """
        super().__init__()
        self._controller = controller
        self._request_factory = request_factory
        self._dialog_presenter = dialog_presenter or QtDialogPresenter()
        self._settings_dialog_factory = settings_dialog_factory
        self._url_input = QLineEdit(self)
        self._output_input = QLineEdit(self)
        self._settings_button = QPushButton("Settings", self)
        self._generate_button = QPushButton("Generate", self)
        self._cancel_button = QPushButton("Cancel", self)
        self._progress_bar = QProgressBar(self)
        self._status_label = QLabel(self)
        self._log_panel = QPlainTextEdit(self)
        self._build_ui()
        self._connect_signals()
        self._apply_view_state(GenerationViewState(GenerationStatus.IDLE, 0, "Ready"))

    def form_data(self) -> GenerationFormData:
        """Return immutable form values without performing validation or I/O."""
        return GenerationFormData(self._url_input.text().strip(), Path(self._output_input.text().strip()))

    def closeEvent(self, event: QCloseEvent) -> None:
        """Protect the window while a background generation remains active."""
        if not self._controller.is_running:
            event.accept()
            return
        if self._dialog_presenter.confirm_close(self):
            self._controller.request_cancellation()
            self._apply_view_state(GenerationViewState(GenerationStatus.RUNNING, 0, "Cancellation requested"))
        event.ignore()

    def _build_ui(self) -> None:
        """Create static generation controls and placeholder presentation widgets."""
        self.setWindowTitle("AI-Clipper")
        self._url_input.setPlaceholderText("YouTube URL")
        self._output_input.setPlaceholderText("Output folder")
        self._progress_bar.setRange(0, 100)
        self._log_panel.setReadOnly(True)
        self._cancel_button.setEnabled(False)
        form_layout = QFormLayout()
        form_layout.addRow("YouTube URL", self._url_input)
        form_layout.addRow("Output folder", self._output_input)
        actions = QHBoxLayout()
        actions.addWidget(self._settings_button)
        actions.addWidget(self._generate_button)
        actions.addWidget(self._cancel_button)
        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addLayout(actions)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_label)
        layout.addWidget(self._log_panel)
        container = QWidget(self)
        container.setLayout(layout)
        self.setCentralWidget(container)

    def _connect_signals(self) -> None:
        """Connect UI actions and controller events using signal-slot communication."""
        self._generate_button.clicked.connect(self._submit_generation)
        self._cancel_button.clicked.connect(self._request_cancellation)
        self._settings_button.clicked.connect(self._show_settings)
        self._controller.progress_updated.connect(self._on_progress_updated)
        self._controller.generation_started.connect(self._on_generation_started)
        self._controller.generation_completed.connect(self._on_generation_completed)
        self._controller.generation_failed.connect(self._on_generation_failed)
        self._controller.generation_cancelled.connect(self._on_generation_cancelled)
        self._controller.generation_finished.connect(self._on_generation_finished)

    def _submit_generation(self) -> None:
        """Build and submit one request without executing work in the UI thread."""
        try:
            request = self._request_factory(self.form_data())
            self.generation_requested.emit(request)
            self._controller.start_generation(request)
        except (GuiError, ApplicationExecutionError) as error:
            self._show_error("Generation unavailable", str(error))
        except Exception:
            self._show_error("Invalid request", "Unable to start generation with the supplied values.")

    def _request_cancellation(self) -> None:
        """Send a basic cancellation request without blocking the interface."""
        self._controller.request_cancellation()
        self._apply_view_state(GenerationViewState(GenerationStatus.RUNNING, 0, "Cancellation requested"))

    def _show_settings(self) -> None:
        """Open the non-persistent placeholder settings dialog."""
        self._settings_dialog_factory(self).exec()

    def _on_generation_started(self) -> None:
        """Disable duplicate submissions while the worker owns the active job."""
        self._generate_button.setEnabled(False)
        self._cancel_button.setEnabled(True)
        self._apply_view_state(GenerationViewState(GenerationStatus.RUNNING, 0, "Generation started"))

    def _on_progress_updated(self, progress: ApplicationProgress) -> None:
        """Update presentation state from an application progress event."""
        pipeline_progress = progress.pipeline_progress
        percentage = int(
            pipeline_progress.stage_progress_percentage
            if pipeline_progress.stage_progress_percentage is not None
            else (pipeline_progress.completed_stages / pipeline_progress.total_stages) * 100
        )
        message = pipeline_progress.message or pipeline_progress.stage.value.replace("_", " ").title()
        self._apply_view_state(GenerationViewState(GenerationStatus.RUNNING, percentage, message))

    def _on_generation_completed(self, _: object) -> None:
        """Display the successful terminal state emitted by the controller."""
        self._apply_view_state(GenerationViewState(GenerationStatus.COMPLETED, 100, "Generation completed"))

    def _on_generation_failed(self, error: object) -> None:
        """Display a safe failure state and dialog without exposing tracebacks."""
        message = str(error)
        self._apply_view_state(GenerationViewState(GenerationStatus.FAILED, 0, message))
        self._show_error("Generation failed", message)

    def _on_generation_cancelled(self) -> None:
        """Display the terminal cancellation state emitted by the controller."""
        self._apply_view_state(GenerationViewState(GenerationStatus.IDLE, 0, "Generation cancelled"))

    def _on_generation_finished(self) -> None:
        """Restore controls once the thread has fully released its active job."""
        self._generate_button.setEnabled(True)
        self._cancel_button.setEnabled(False)

    def _show_error(self, title: str, message: str) -> None:
        """Delegate user-safe error presentation to the injected dialog boundary."""
        self._dialog_presenter.show_error(self, title, message)

    def _apply_view_state(self, state: GenerationViewState) -> None:
        """Render one immutable presentation state into existing widgets."""
        self._progress_bar.setValue(state.progress_percentage)
        self._status_label.setText(state.message)
        self._log_panel.appendPlainText(f"{state.status.value}: {state.message}")
