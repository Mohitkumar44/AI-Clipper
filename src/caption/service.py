"""Application service for provider-independent caption-data generation."""

from __future__ import annotations

import logging

from .exceptions import CaptionError, CaptionGenerationError
from .models import (
    CaptionConfiguration,
    CaptionProgress,
    CaptionRequest,
    CaptionResult,
    CaptionSegment,
    CaptionStatus,
    ProgressCallback,
)
from .validator import validate_caption_request, validate_caption_result


class CaptionService:
    """Generate timestamp-preserving immutable caption segments from transcripts."""

    def __init__(self, logger: logging.Logger) -> None:
        """Initialize caption generation with an injected structured logger.

        Args:
            logger: Application logger supplied by the composition root.
        """
        self._logger = logger

    def generate(
        self,
        request: CaptionRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> CaptionResult:
        """Generate readable caption segments scoped to one rendered clip.

        Args:
            request: Immutable transcript, clip, and segmentation configuration.
            progress_callback: Optional receiver of normalized caption progress.

        Returns:
            Immutable timestamp-preserving caption data.

        Raises:
            CaptionError: If validation or segmentation cannot complete safely.
        """
        validate_caption_request(request)
        source_segments = tuple(
            segment
            for segment in request.transcript_result.segments
            if segment.end_seconds > request.rendered_clip.start_seconds
            and segment.start_seconds < request.rendered_clip.end_seconds
        )
        self._emit(progress_callback, CaptionProgress(CaptionStatus.PREPARING, 0, len(source_segments)))
        caption_segments: list[CaptionSegment] = []
        try:
            for index, transcript_segment in enumerate(source_segments, start=1):
                for lines in _segment_lines(transcript_segment.text, request.configuration):
                    caption_segments.append(
                        CaptionSegment(transcript_segment.start_seconds, transcript_segment.end_seconds, lines)
                    )
                self._emit(progress_callback, CaptionProgress(CaptionStatus.SEGMENTING, index, len(source_segments)))
            result = CaptionResult(request.rendered_clip, tuple(caption_segments))
            validate_caption_result(result, request.configuration)
        except CaptionError:
            raise
        except Exception as error:
            self._logger.exception("caption_generation_failed", extra={"event": "caption_generation_failed"})
            raise CaptionGenerationError("Caption generation failed unexpectedly.") from error
        self._emit(progress_callback, CaptionProgress(CaptionStatus.COMPLETED, len(source_segments), len(source_segments)))
        self._logger.info("caption_generation_completed", extra={"event": "caption_generation_completed"})
        return result

    def _emit(self, callback: ProgressCallback | None, progress: CaptionProgress) -> None:
        """Notify callers without allowing callback failures to interrupt generation."""
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            self._logger.exception("caption_progress_callback_failed", extra={"event": "progress_callback_failed"})


def _segment_lines(text: str, configuration: CaptionConfiguration) -> tuple[tuple[str, ...], ...]:
    """Split text at word boundaries into configured caption display groups."""
    words = text.split()
    if not words:
        return ()
    lines: list[str] = []
    current_line = ""
    for word in words:
        proposed = word if not current_line else f"{current_line} {word}"
        if current_line and len(proposed) > configuration.maximum_characters_per_line:
            lines.append(current_line)
            current_line = word
        else:
            current_line = proposed
    if current_line:
        lines.append(current_line)
    return tuple(
        tuple(lines[index : index + configuration.maximum_lines_per_caption])
        for index in range(0, len(lines), configuration.maximum_lines_per_caption)
    )
