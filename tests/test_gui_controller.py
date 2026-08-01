"""In-memory tests for GUI controller, thread wiring, and window presentation."""

import logging
import sys
import types

import pytest


def _install_qt_stub() -> None:
    """Install a small in-memory Qt API used only when PySide6 is unavailable."""
    if "PySide6" in sys.modules:
        return

    class BoundSignal:
        def __init__(self) -> None: self._callbacks = []
        def connect(self, callback) -> None: self._callbacks.append(callback)
        def __call__(self, *args) -> None: self.emit(*args)
        def emit(self, *args) -> None:
            for callback in tuple(self._callbacks): callback(*args)

    class Signal:
        def __init__(self, *_: object) -> None: self._name = ""
        def __set_name__(self, _: object, name: str) -> None: self._name = name
        def __get__(self, instance: object, _: object) -> BoundSignal | "Signal":
            if instance is None: return self
            signal = instance.__dict__.get(self._name)
            if signal is None:
                signal = BoundSignal(); instance.__dict__[self._name] = signal
            return signal

    class QObject:
        def __init__(self, *_: object) -> None: pass
        def moveToThread(self, _: object) -> None: pass
        def deleteLater(self) -> None: pass

    class QThread(QObject):
        started = Signal(); finished = Signal()
        def __init__(self, *_: object) -> None: super().__init__(); self._running = False
        def start(self) -> None: self._running = True
        def quit(self) -> None:
            self._running = False; self.finished.emit()
        def isRunning(self) -> bool: return self._running

    class QCloseEvent:
        def __init__(self) -> None: self._accepted = False
        def accept(self) -> None: self._accepted = True
        def ignore(self) -> None: self._accepted = False
        def isAccepted(self) -> bool: return self._accepted

    class QWidget(QObject):
        def __init__(self, *_: object) -> None: super().__init__()
        def setLayout(self, _: object) -> None: pass

    class QMainWindow(QWidget):
        def setWindowTitle(self, _: str) -> None: pass
        def setCentralWidget(self, _: QWidget) -> None: pass

    class QDialog(QWidget):
        def setWindowTitle(self, _: str) -> None: pass
        def exec(self) -> int: return 0
        def reject(self) -> None: pass

    class QLineEdit(QWidget):
        def __init__(self, *_: object) -> None: super().__init__(); self._text = ""
        def setPlaceholderText(self, _: str) -> None: pass
        def text(self) -> str: return self._text

    class QPushButton(QWidget):
        clicked = Signal()
        def __init__(self, *_: object) -> None: super().__init__(); self._enabled = True
        def setEnabled(self, value: bool) -> None: self._enabled = value
        def isEnabled(self) -> bool: return self._enabled

    class QLabel(QWidget):
        def __init__(self, *_: object) -> None: super().__init__(); self.text_value = ""
        def setText(self, text: str) -> None: self.text_value = text

    class QProgressBar(QWidget):
        def __init__(self, *_: object) -> None: super().__init__(); self.value = 0
        def setRange(self, *_: int) -> None: pass
        def setValue(self, value: int) -> None: self.value = value

    class QPlainTextEdit(QWidget):
        def setReadOnly(self, _: bool) -> None: pass
        def appendPlainText(self, _: str) -> None: pass

    class Layout:
        def __init__(self, *_: object) -> None: pass
        def addRow(self, *_: object) -> None: pass
        def addWidget(self, *_: object) -> None: pass
        def addLayout(self, *_: object) -> None: pass

    class QDialogButtonBox(QWidget):
        rejected = Signal()
        class StandardButton: Close = 1; Yes = 2; No = 4
        def __init__(self, *_: object) -> None: super().__init__()

    class QMessageBox:
        StandardButton = QDialogButtonBox.StandardButton
        @staticmethod
        def critical(*_: object) -> None: pass
        @staticmethod
        def question(*_: object) -> int: return QDialogButtonBox.StandardButton.No

    package = types.ModuleType("PySide6")
    core = types.ModuleType("PySide6.QtCore")
    core.QObject, core.QThread, core.Signal = QObject, QThread, Signal
    core.Slot = lambda *_, **__: lambda function: function
    gui = types.ModuleType("PySide6.QtGui"); gui.QCloseEvent = QCloseEvent
    widgets = types.ModuleType("PySide6.QtWidgets")
    for name, value in {
        "QDialog": QDialog, "QDialogButtonBox": QDialogButtonBox, "QFormLayout": Layout,
        "QHBoxLayout": Layout, "QLabel": QLabel, "QLineEdit": QLineEdit, "QMainWindow": QMainWindow,
        "QMessageBox": QMessageBox, "QPlainTextEdit": QPlainTextEdit, "QProgressBar": QProgressBar,
        "QPushButton": QPushButton, "QVBoxLayout": Layout, "QWidget": QWidget,
    }.items(): setattr(widgets, name, value)
    sys.modules.update({"PySide6": package, "PySide6.QtCore": core, "PySide6.QtGui": gui, "PySide6.QtWidgets": widgets})


_install_qt_stub()

from PySide6.QtGui import QCloseEvent
from src.application.exceptions import ApplicationError
from src.application.models import ApplicationRequest
from src.gui.controller import GenerationController
from src.gui.exceptions import ApplicationExecutionError
from src.gui.main_window import MainWindow


class FakeApplicationService:
    """Application facade fake that emits only in-memory progress and results."""
    def __init__(self, result: object = "result", error: Exception | None = None) -> None:
        self.result, self.error = result, error
    def run(self, _: object, callback) -> object:
        if self.error: raise self.error
        callback("progress")
        return self.result


class FakeDialogs:
    """Injected safe-dialog fake recording user-facing messages."""
    def __init__(self, confirm: bool = False) -> None: self.confirm, self.errors = confirm, []
    def show_error(self, _, title: str, message: str) -> None: self.errors.append((title, message))
    def confirm_close(self, _) -> bool: return self.confirm


class FakeSettingsDialog:
    """Placeholder settings fake with no GUI side effects."""
    def __init__(self) -> None: self.opened = False
    def exec(self) -> int: self.opened = True; return 0


def test_controller_worker_lifecycle_progress_completion_and_cancellation() -> None:
    """Controller owns worker startup, relay signals, completion, and cancellation."""
    controller = GenerationController(FakeApplicationService(), logging.getLogger("gui-test"))  # type: ignore[arg-type]
    progress, completed, finished, cancelled = [], [], [], []
    controller.progress_updated.connect(progress.append)
    controller.generation_completed.connect(completed.append)
    controller.generation_finished.connect(lambda: finished.append(True))
    controller.generation_cancelled.connect(lambda: cancelled.append(True))
    controller.start_generation(ApplicationRequest(None))  # type: ignore[arg-type]
    with pytest.raises(ApplicationExecutionError): controller.start_generation(ApplicationRequest(None))  # type: ignore[arg-type]
    controller._thread.started.emit()
    assert progress == ["progress"] and completed == ["result"] and finished == [True]
    controller.start_generation(ApplicationRequest(None))  # type: ignore[arg-type]
    controller.request_cancellation()
    controller._thread.started.emit()
    assert cancelled == [True] and not controller.is_running


def test_controller_forwards_worker_failure_as_gui_error() -> None:
    """Application failures surface as stable GUI failure signals."""
    controller = GenerationController(FakeApplicationService(error=ApplicationError("failed")), logging.getLogger("gui-test"))  # type: ignore[arg-type]
    failures = []
    controller.generation_failed.connect(failures.append)
    controller.start_generation(ApplicationRequest(None))  # type: ignore[arg-type]
    controller._thread.started.emit()
    assert isinstance(failures[0], ApplicationExecutionError)


def test_main_window_updates_controls_progress_dialogs_and_close_protection() -> None:
    """Window logic updates only presentation widgets and delegates control actions."""
    controller = GenerationController(FakeApplicationService(), logging.getLogger("gui-test"))  # type: ignore[arg-type]
    dialogs, settings = FakeDialogs(confirm=True), FakeSettingsDialog()
    window = MainWindow(controller, lambda _: ApplicationRequest(None), dialogs, lambda _: settings)  # type: ignore[arg-type]
    window._submit_generation()
    assert not window._generate_button.isEnabled() and window._cancel_button.isEnabled()
    window._on_progress_updated(types.SimpleNamespace(pipeline_progress=types.SimpleNamespace(stage_progress_percentage=50, completed_stages=2, total_stages=4, message="Working", stage=types.SimpleNamespace(value="rendering"))))
    assert window._progress_bar.value == 50 and window._status_label.text_value == "Working"
    window._show_settings(); assert settings.opened
    window._on_generation_failed(ApplicationExecutionError("safe")); assert dialogs.errors[-1] == ("Generation failed", "safe")
    event = QCloseEvent(); window.closeEvent(event); assert not event.isAccepted()
    window._thread = None if False else None
    controller._thread.started.emit()


def test_main_window_handles_invalid_request_composition() -> None:
    """Request construction errors produce a safe presentation message."""
    dialogs = FakeDialogs()
    window = MainWindow(GenerationController(FakeApplicationService(), logging.getLogger("gui-test")), lambda _: (_ for _ in ()).throw(ValueError()), dialogs)  # type: ignore[arg-type]
    window._submit_generation()
    assert dialogs.errors == [("Invalid request", "Unable to start generation with the supplied values.")]
