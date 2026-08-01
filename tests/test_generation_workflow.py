"""Headless in-memory tests for the GUI Generate workflow."""

import logging
import sys
import types
from pathlib import Path

import pytest


def _install_qt_stub() -> None:
    """Provide the minimal Qt surface required by GUI workflow tests."""
    class BoundSignal:
        def __init__(self): self.callbacks = []
        def connect(self, callback): self.callbacks.append(callback)
        def emit(self, *args):
            for callback in tuple(self.callbacks): callback(*args)
        def __call__(self, *args): self.emit(*args)
    class Signal:
        def __init__(self, *_): self.name = ""
        def __set_name__(self, _, name): self.name = name
        def __get__(self, instance, _):
            if instance is None: return self
            instance.__dict__.setdefault(self.name, BoundSignal()); return instance.__dict__[self.name]
    class QObject:
        def __init__(self, *_): pass
        def moveToThread(self, _): pass
        def deleteLater(self): pass
    class QThread(QObject):
        started = Signal(); finished = Signal()
        def __init__(self, *_): super().__init__(); self.running = False
        def start(self): self.running = True
        def quit(self): self.running = False; self.finished.emit()
        def isRunning(self): return self.running
        def deleteLater(self): pass
    class QWidget(QObject):
        def setLayout(self, _): pass
    class QMainWindow(QWidget):
        def setWindowTitle(self, _): pass
        def setCentralWidget(self, _): pass
    class QDialog(QWidget):
        def setWindowTitle(self, _): pass
        def exec(self): return 0
        def reject(self): pass
    class LineEdit(QWidget):
        def __init__(self, *_): self.value = ""
        def setPlaceholderText(self, _): pass
        def text(self): return self.value
    class Button(QWidget):
        clicked = Signal()
        def __init__(self, *_): self.enabled = True
        def setEnabled(self, value): self.enabled = value
        def isEnabled(self): return self.enabled
    class Label(QWidget):
        def __init__(self, *_): self.value = ""
        def setText(self, value): self.value = value
    class Progress(QWidget):
        def __init__(self, *_): self.value = 0
        def setRange(self, *_): pass
        def setValue(self, value): self.value = value
    class Log(QWidget):
        def __init__(self, *_): self.entries = []
        def setReadOnly(self, _): pass
        def appendPlainText(self, value): self.entries.append(value)
    class Layout:
        def __init__(self, *_): pass
        def addRow(self, *_): pass
        def addWidget(self, *_): pass
        def addLayout(self, *_): pass
    class ButtonBox(QWidget):
        rejected = Signal()
        class StandardButton: Close = 1; Yes = 2; No = 4
        def __init__(self, *_): pass
    class MessageBox:
        StandardButton = ButtonBox.StandardButton
        errors = []
        @classmethod
        def critical(cls, *args): cls.errors.append(args)
        @staticmethod
        def question(*_): return ButtonBox.StandardButton.No
    class CloseEvent:
        def __init__(self): self.accepted = False
        def accept(self): self.accepted = True
        def ignore(self): self.accepted = False
        def isAccepted(self): return self.accepted
    package, core = types.ModuleType("PySide6"), types.ModuleType("PySide6.QtCore")
    core.QObject, core.QThread, core.Signal = QObject, QThread, Signal
    core.Slot = lambda *_, **__: lambda function: function
    gui = types.ModuleType("PySide6.QtGui"); gui.QCloseEvent = CloseEvent
    widgets = types.ModuleType("PySide6.QtWidgets")
    for name, value in {"QDialog": QDialog, "QDialogButtonBox": ButtonBox, "QFormLayout": Layout,
        "QHBoxLayout": Layout, "QLabel": Label, "QLineEdit": LineEdit, "QMainWindow": QMainWindow,
        "QMessageBox": MessageBox, "QPlainTextEdit": Log, "QProgressBar": Progress,
        "QPushButton": Button, "QVBoxLayout": Layout, "QWidget": QWidget}.items(): setattr(widgets, name, value)
    sys.modules.update({"PySide6": package, "PySide6.QtCore": core, "PySide6.QtGui": gui, "PySide6.QtWidgets": widgets})


_install_qt_stub()

from src.application.exceptions import ApplicationError
from src.application.models import ApplicationRequest
from src.gui.controller import GenerationController
from src.gui.exceptions import ApplicationExecutionError, InvalidGenerationFormError
from src.gui.main_window import MainWindow, QtDialogPresenter, validate_generation_form
from src.gui.models import GenerationFormData
from src.gui.worker import GenerationWorker


class InMemoryDirectory:
    """Path-shaped in-memory directory value used by validation tests."""
    def __init__(self, exists: bool): self.exists = exists
    def is_dir(self): return self.exists


class FakeApplicationService:
    """Application facade fake that never enters any backend service."""
    def __init__(self, error: Exception | None = None): self.error, self.calls = error, 0
    def run(self, _, callback):
        self.calls += 1
        if self.error: raise self.error
        callback(types.SimpleNamespace(pipeline_progress=types.SimpleNamespace(
            stage_progress_percentage=55, completed_stages=2, total_stages=4,
            message="Rendering clips", stage=types.SimpleNamespace(value="rendering"))))
        return "completed"


class FakeDialogs:
    """Dialog presenter fake that records safe user messages."""
    def __init__(self): self.errors = []; self.confirm = False
    def show_error(self, _, title, message): self.errors.append((title, message))
    def confirm_close(self, _): return self.confirm


def _window(service: FakeApplicationService, validator=lambda _: None):
    """Create a window with real controller/worker wiring and in-memory dependencies."""
    dialogs = FakeDialogs()
    controller = GenerationController(service, logging.getLogger("test.workflow"))  # type: ignore[arg-type]
    factory_calls = []
    def request_factory(form): factory_calls.append(form); return ApplicationRequest(None)  # type: ignore[arg-type]
    window = MainWindow(controller, request_factory, dialogs, form_validator=validator)
    window._url_input.value = "https://www.youtube.com/watch?v=valid"
    window._output_input.value = "output"
    return window, controller, dialogs, factory_calls


def test_generate_starts_worker_updates_progress_and_restores_buttons() -> None:
    """Clicking Generate validates, composes, starts work, and restores the UI."""
    window, controller, dialogs, calls = _window(FakeApplicationService())
    window._submit_generation()
    assert calls and not window._generate_button.isEnabled() and window._cancel_button.isEnabled()
    controller._thread.started.emit()
    assert any("Rendering clips" in entry for entry in window._log_panel.entries)
    assert window._progress_bar.value == 100
    assert window._status_label.value == "Generation completed"
    assert window._generate_button.isEnabled() and not window._cancel_button.isEnabled()
    assert not dialogs.errors


def test_invalid_youtube_url_and_output_directory_are_rejected_before_request_factory() -> None:
    """Pure UI validation prevents invalid form data from starting a job."""
    with pytest.raises(InvalidGenerationFormError):
        validate_generation_form(GenerationFormData("https://example.com/video", InMemoryDirectory(True)))  # type: ignore[arg-type]
    with pytest.raises(InvalidGenerationFormError):
        validate_generation_form(GenerationFormData("https://youtu.be/video", InMemoryDirectory(False)))  # type: ignore[arg-type]
    window, _, dialogs, calls = _window(FakeApplicationService(), lambda _: (_ for _ in ()).throw(InvalidGenerationFormError("invalid")))
    window._submit_generation()
    assert calls == [] and dialogs.errors == [("Invalid generation request", "invalid")]


def test_failure_and_cancel_workflows_restore_controls_and_show_safe_errors() -> None:
    """Failure and cancellation are terminal UI paths without backend execution."""
    failed_window, failed_controller, failed_dialogs, _ = _window(FakeApplicationService(ApplicationError("failed")))
    failed_window._submit_generation(); failed_controller._thread.started.emit()
    assert failed_dialogs.errors[-1] == ("Generation failed", "Generation could not be completed.")
    assert failed_window._generate_button.isEnabled() and not failed_window._cancel_button.isEnabled()
    cancelled_window, cancelled_controller, _, _ = _window(FakeApplicationService())
    cancelled_window._submit_generation(); cancelled_window._request_cancellation(); cancelled_controller._thread.started.emit()
    assert cancelled_window._status_label.value == "Generation cancelled"
    assert cancelled_window._generate_button.isEnabled() and not cancelled_window._cancel_button.isEnabled()


def test_worker_translation_progress_and_dialog_presenter_are_safe() -> None:
    """Worker and dialog helpers preserve stable GUI behavior at the boundary."""
    worker = GenerationWorker(FakeApplicationService(ApplicationError("failed")), ApplicationRequest(None), logging.getLogger("test.workflow"))  # type: ignore[arg-type]
    failures = []; worker.generation_failed.connect(failures.append); worker.run()
    assert isinstance(failures[0], ApplicationExecutionError)
    presenter = QtDialogPresenter(); presenter.show_error(object(), "title", "message")  # type: ignore[arg-type]


def test_settings_and_close_protection_cover_non_running_and_rejected_paths() -> None:
    """Settings remains a placeholder and close protection never closes active work."""
    window, controller, _, _ = _window(FakeApplicationService())
    from src.gui.dialogs.settings_dialog import SettingsDialog
    assert SettingsDialog(window).exec() == 0
    from PySide6.QtGui import QCloseEvent
    idle_event = QCloseEvent(); window.closeEvent(idle_event); assert idle_event.isAccepted()
    window._submit_generation()
    rejected_event = QCloseEvent(); window.closeEvent(rejected_event)
    assert not rejected_event.isAccepted() and controller.is_running
