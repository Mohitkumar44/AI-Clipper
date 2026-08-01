"""In-memory lifecycle tests for GenerationWorker."""

import logging
import sys
import types

if "PySide6.QtCore" not in sys.modules:
    package, core = types.ModuleType("PySide6"), types.ModuleType("PySide6.QtCore")
    class BoundSignal:
        def __init__(self): self.callbacks = []
        def connect(self, callback): self.callbacks.append(callback)
        def emit(self, *args): [callback(*args) for callback in tuple(self.callbacks)]
    class Signal:
        def __init__(self, *_): self.name = ""
        def __set_name__(self, _, name): self.name = name
        def __get__(self, instance, _):
            if instance is None: return self
            instance.__dict__.setdefault(self.name, BoundSignal()); return instance.__dict__[self.name]
    class QObject:
        def __init__(self, *_): pass
    core.QObject, core.Signal, core.Slot = QObject, Signal, lambda *_, **__: lambda function: function
    sys.modules.update({"PySide6": package, "PySide6.QtCore": core})

from src.application.exceptions import ApplicationError
from src.application.models import ApplicationRequest
from src.gui.exceptions import ApplicationExecutionError
from src.gui.worker import GenerationWorker


class FakeApplicationService:
    """In-memory application facade fake."""
    def __init__(self, error: Exception | None = None): self.error, self.calls = error, 0
    def run(self, _, callback):
        self.calls += 1
        if self.error: raise self.error
        callback("progress"); return "complete"


def test_worker_forwards_progress_completes_and_finishes() -> None:
    """Successful work emits immutable lifecycle payloads in memory."""
    worker = GenerationWorker(FakeApplicationService(), ApplicationRequest(None), logging.getLogger("gui-test"))  # type: ignore[arg-type]
    progress, completed, finished = [], [], []
    worker.progress_updated.connect(progress.append); worker.generation_completed.connect(completed.append); worker.finished.connect(lambda: finished.append(True))
    worker.run()
    assert progress == ["progress"] and completed == ["complete"] and finished == [True]


def test_worker_translates_failures_and_honors_cancellation() -> None:
    """Failure and cancellation never expose application internals or execute cancelled work."""
    failing = GenerationWorker(FakeApplicationService(ApplicationError("bad")), ApplicationRequest(None), logging.getLogger("gui-test"))  # type: ignore[arg-type]
    failures = []; failing.generation_failed.connect(failures.append); failing.run()
    assert isinstance(failures[0], ApplicationExecutionError)
    service = FakeApplicationService(); cancelled = GenerationWorker(service, ApplicationRequest(None), logging.getLogger("gui-test"))  # type: ignore[arg-type]
    events = []; cancelled.generation_cancelled.connect(lambda: events.append(True)); cancelled.request_cancellation(); cancelled.run()
    assert events == [True] and service.calls == 0
