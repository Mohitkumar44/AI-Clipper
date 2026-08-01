"""Tests for immutable transcript data models."""

from pathlib import Path

import pytest

from src.transcript.models import (
    LanguageInfo,
    TranscriptConfig,
    TranscriptProgress,
    TranscriptRequest,
    TranscriptResult,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptTask,
)


def test_transcript_config_is_immutable() -> None:
    """Configuration retains provider-independent request settings."""
    config = TranscriptConfig(model_name="small", word_timestamps=True)
    assert config.device == "cpu"
    with pytest.raises(AttributeError):
        config.model_name = "medium"  # type: ignore[misc]


def test_transcript_request_keeps_path_and_task() -> None:
    """Requests use pathlib and explicit task enums."""
    request = TranscriptRequest(
        media_path=Path("video.mp4"),
        config=TranscriptConfig(model_name="small"),
        task=TranscriptTask.TRANSLATE,
    )
    assert request.media_path == Path("video.mp4")
    assert request.task is TranscriptTask.TRANSLATE


def test_result_contains_timestamped_segments() -> None:
    """Results preserve the analysis handoff contract."""
    segment = TranscriptSegment(0, 0.0, 1.5, "Hello")
    result = TranscriptResult(
        source_path=Path("video.mp4"),
        full_text="Hello",
        segments=(segment,),
        language=LanguageInfo("en", "English", detected=True),
        backend_name="fake",
        processing_time_seconds=0.5,
    )
    assert result.segments[0].end_seconds == 1.5
    assert result.language.detected is True


def test_progress_preserves_optional_measurements() -> None:
    """Progress can represent an indeterminate operation."""
    progress = TranscriptProgress(status=TranscriptStatus.LOADING_MODEL)
    assert progress.progress_percentage is None
    assert progress.status is TranscriptStatus.LOADING_MODEL
