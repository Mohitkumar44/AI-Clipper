"""In-memory tests for the high-level ApplicationService facade."""

import logging

import pytest

from src.application.exceptions import ApplicationPipelineError, InvalidApplicationRequestError
from src.application.models import ApplicationRequest
from src.application.service import ApplicationService
from src.pipeline.exceptions import PipelineError
from src.pipeline.models import PipelineProgress, PipelineStage


class FakePipelineService:
    """In-memory pipeline fake that never reaches external systems."""

    def __init__(self, result: object = "completed", error: Exception | None = None) -> None:
        """Configure a deterministic result or failure."""
        self.result = result
        self.error = error
        self.received_request: object | None = None

    def run(self, request: object, progress_callback=None) -> object:
        """Return configured data while optionally emitting one progress event."""
        self.received_request = request
        if self.error is not None:
            raise self.error
        if progress_callback is not None:
            progress_callback(PipelineProgress(PipelineStage.COMPLETED, 4, 4))
        return self.result


def test_application_service_runs_pipeline_and_forwards_progress() -> None:
    """The single public method delegates and wraps its pipeline output."""
    pipeline = FakePipelineService()
    events = []
    request = ApplicationRequest(None)  # type: ignore[arg-type]

    result = ApplicationService(pipeline, logging.getLogger("test.application")).run(request, events.append)  # type: ignore[arg-type]

    assert result.pipeline_result == "completed"
    assert pipeline.received_request is None
    assert events[0].pipeline_progress.stage is PipelineStage.COMPLETED


@pytest.mark.parametrize("error", [PipelineError("failed"), RuntimeError("unexpected")])
def test_application_service_translates_pipeline_failures(error: Exception) -> None:
    """No pipeline or unexpected exception crosses the application boundary."""
    service = ApplicationService(FakePipelineService(error=error), logging.getLogger("test.application"))  # type: ignore[arg-type]
    with pytest.raises(ApplicationPipelineError) as raised:
        service.run(ApplicationRequest(None))  # type: ignore[arg-type]
    assert raised.value.__cause__ is error


def test_application_service_rejects_invalid_request_and_callback_errors() -> None:
    """Input and caller callback failures remain safely isolated."""
    service = ApplicationService(FakePipelineService(), logging.getLogger("test.application"))  # type: ignore[arg-type]
    with pytest.raises(InvalidApplicationRequestError):
        service.run(object())  # type: ignore[arg-type]
    result = service.run(
        ApplicationRequest(None),  # type: ignore[arg-type]
        lambda _: (_ for _ in ()).throw(RuntimeError("callback")),
    )
    assert result.pipeline_result == "completed"
