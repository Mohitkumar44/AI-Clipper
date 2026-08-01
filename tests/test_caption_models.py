"""Tests for immutable caption models."""
import pytest
from src.caption.models import CaptionConfiguration, CaptionProgress, CaptionStatus

def test_caption_models_are_immutable() -> None:
    configuration = CaptionConfiguration(20, 2)
    assert CaptionProgress(CaptionStatus.PREPARING).status is CaptionStatus.PREPARING
    with pytest.raises(AttributeError): configuration.maximum_characters_per_line = 10  # type: ignore[misc]
