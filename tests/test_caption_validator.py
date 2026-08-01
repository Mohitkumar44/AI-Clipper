"""Tests for pure caption validation."""

from dataclasses import replace
from pathlib import Path

import pytest
from src.caption.exceptions import CaptionValidationError, InvalidCaptionRequestError
from src.caption.models import CaptionConfiguration, CaptionRequest, CaptionResult, CaptionSegment
from src.caption.validator import (
    validate_caption_configuration,
    validate_caption_request,
    validate_caption_result,
    validate_caption_segment,
)
from src.clipper.models import ClipFormat, RenderedClip
from src.transcript.models import LanguageInfo, TranscriptResult, TranscriptSegment


def _request() -> CaptionRequest:
    """Create a valid in-memory caption request."""
    transcript = TranscriptResult(
        Path("source.mp4"),
        "Hello world",
        (TranscriptSegment(0, 0, 2, "Hello world"),),
        LanguageInfo("en", "English", True),
        "test",
        0,
    )
    clip = RenderedClip("clip", Path("clip.mp4"), 0, 2, ClipFormat.MP4, 2)
    return CaptionRequest(transcript, clip, CaptionConfiguration(10, 2))

def test_caption_configuration_and_segments_validate() -> None:
    configuration = CaptionConfiguration(10, 2)
    assert validate_caption_configuration(configuration) is configuration
    assert validate_caption_segment(CaptionSegment(0, 1, ("Hello",)), configuration).lines == ("Hello",)

@pytest.mark.parametrize("configuration", [CaptionConfiguration(0, 2), CaptionConfiguration(10, 0)])
def test_invalid_configuration_is_rejected(configuration: CaptionConfiguration) -> None:
    with pytest.raises(InvalidCaptionRequestError): validate_caption_configuration(configuration)


def test_request_validation_rejects_invalid_types_and_timestamps() -> None:
    request = _request()
    assert validate_caption_request(request) is request
    with pytest.raises(InvalidCaptionRequestError):
        validate_caption_request(object())  # type: ignore[arg-type]
    invalid_clip = replace(request.rendered_clip, end_seconds=0)
    with pytest.raises(InvalidCaptionRequestError):
        validate_caption_request(replace(request, rendered_clip=invalid_clip))
    with pytest.raises(InvalidCaptionRequestError):
        validate_caption_configuration(object())  # type: ignore[arg-type]

def test_invalid_caption_segment_is_rejected() -> None:
    with pytest.raises(CaptionValidationError): validate_caption_segment(CaptionSegment(1, 0, ("Hello",)), CaptionConfiguration())
    with pytest.raises(CaptionValidationError): validate_caption_segment(CaptionSegment(0, 1, ("x" * 50,)), CaptionConfiguration())
    with pytest.raises(CaptionValidationError):
        validate_caption_segment(object(), CaptionConfiguration())  # type: ignore[arg-type]
    with pytest.raises(CaptionValidationError):
        validate_caption_segment(CaptionSegment(0, 1, ()), CaptionConfiguration())


def test_caption_result_validation_enforces_type_and_timestamp_order() -> None:
    request = _request()
    result = CaptionResult(
        request.rendered_clip,
        (CaptionSegment(0, 1, ("Hello",)), CaptionSegment(1, 2, ("world",))),
    )
    assert validate_caption_result(result, request.configuration) is result
    with pytest.raises(CaptionValidationError):
        validate_caption_result(object(), request.configuration)  # type: ignore[arg-type]
    unordered = CaptionResult(
        request.rendered_clip,
        (CaptionSegment(1, 2, ("later",)), CaptionSegment(0, 1, ("earlier",))),
    )
    with pytest.raises(CaptionValidationError):
        validate_caption_result(unordered, request.configuration)
