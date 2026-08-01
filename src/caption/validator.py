"""Pure validation utilities for immutable caption-generation contracts."""

from __future__ import annotations

from .exceptions import CaptionValidationError, InvalidCaptionRequestError
from .models import CaptionConfiguration, CaptionRequest, CaptionResult, CaptionSegment


def validate_caption_request(request: CaptionRequest) -> CaptionRequest:
    """Validate a caption request without reading files or rendering subtitles.

    Args:
        request: Immutable caption-generation request.

    Returns:
        The original validated request.

    Raises:
        InvalidCaptionRequestError: If the request or its configuration is invalid.
    """
    if not isinstance(request, CaptionRequest):
        raise InvalidCaptionRequestError("request must be a CaptionRequest instance.")
    validate_caption_configuration(request.configuration)
    if request.rendered_clip.end_seconds <= request.rendered_clip.start_seconds:
        raise InvalidCaptionRequestError("rendered_clip timestamps are invalid.")
    return request


def validate_caption_configuration(configuration: CaptionConfiguration) -> CaptionConfiguration:
    """Validate caption readability limits.

    Args:
        configuration: Immutable caption segmentation settings.

    Returns:
        The original validated configuration.

    Raises:
        InvalidCaptionRequestError: If a limit is not a positive integer.
    """
    if not isinstance(configuration, CaptionConfiguration):
        raise InvalidCaptionRequestError("configuration must be a CaptionConfiguration instance.")
    for value, name in (
        (configuration.maximum_characters_per_line, "maximum_characters_per_line"),
        (configuration.maximum_lines_per_caption, "maximum_lines_per_caption"),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise InvalidCaptionRequestError(f"{name} must be a positive integer.")
    return configuration


def validate_caption_segment(segment: CaptionSegment, configuration: CaptionConfiguration) -> CaptionSegment:
    """Validate timestamps and display-line constraints for one caption segment.

    Args:
        segment: Generated caption segment to validate.
        configuration: Limits used to generate its display lines.

    Returns:
        The original validated caption segment.

    Raises:
        CaptionValidationError: If timestamps or line constraints are invalid.
    """
    if not isinstance(segment, CaptionSegment):
        raise CaptionValidationError("segment must be a CaptionSegment instance.")
    if segment.start_seconds < 0 or segment.end_seconds <= segment.start_seconds:
        raise CaptionValidationError("caption segment timestamps are invalid.")
    if not segment.lines or len(segment.lines) > configuration.maximum_lines_per_caption:
        raise CaptionValidationError("caption segment line count is invalid.")
    if any(not line.strip() or len(line) > configuration.maximum_characters_per_line for line in segment.lines):
        raise CaptionValidationError("caption segment lines violate configured limits.")
    return segment


def validate_caption_result(result: CaptionResult, configuration: CaptionConfiguration) -> CaptionResult:
    """Validate all generated caption segments in source order.

    Args:
        result: Generated immutable caption result.
        configuration: Limits used for segmentation.

    Returns:
        The original validated result.

    Raises:
        CaptionValidationError: If result or segment data is invalid.
    """
    if not isinstance(result, CaptionResult):
        raise CaptionValidationError("result must be a CaptionResult instance.")
    previous_start = -1.0
    for segment in result.segments:
        validate_caption_segment(segment, configuration)
        if segment.start_seconds < previous_start:
            raise CaptionValidationError("caption segments must be ordered by timestamp.")
        previous_start = segment.start_seconds
    return result
