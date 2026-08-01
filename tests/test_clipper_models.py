"""Tests for immutable Clip Cutter models."""
from pathlib import Path
import pytest
from src.clipper.models import ClipCandidate, ClipConfiguration, ClipFormat, ClipProgress, ClipStatus, RenderedClip

def test_models_are_immutable() -> None:
    configuration = ClipConfiguration(Path("output"))
    candidate = ClipCandidate("candidate-1", 0.0, 30.0, 90.0, "Hook")
    rendered = RenderedClip("candidate-1", Path("output/clip.mp4"), 0.0, 30.0, ClipFormat.MP4, 30.0)
    assert rendered.output_format is ClipFormat.MP4 and candidate.score == 90.0
    with pytest.raises(AttributeError): configuration.overwrite = True  # type: ignore[misc]

def test_progress_supports_lifecycle_status() -> None:
    assert ClipProgress(ClipStatus.CUTTING, 0, 1).total_clips == 1
