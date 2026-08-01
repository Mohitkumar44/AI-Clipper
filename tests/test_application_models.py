"""Tests for immutable application facade models."""

import pytest

from src.application.models import ApplicationProgress, ApplicationRequest
from src.pipeline.models import PipelineProgress, PipelineStage


def test_application_models_are_immutable() -> None:
    """Public application wrappers cannot be mutated after construction."""
    progress = ApplicationProgress(PipelineProgress(PipelineStage.DOWNLOADING, 0, 4))
    assert progress.pipeline_progress.stage is PipelineStage.DOWNLOADING
    with pytest.raises(AttributeError):
        progress.pipeline_progress = progress.pipeline_progress


def test_application_request_stores_the_pipeline_request() -> None:
    """The facade keeps the pipeline input intact for delegated execution."""
    request = ApplicationRequest(None)  # type: ignore[arg-type]
    assert request.pipeline_request is None
