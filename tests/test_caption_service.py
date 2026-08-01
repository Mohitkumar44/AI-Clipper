"""In-memory tests for caption segmentation service."""
import logging
from pathlib import Path
import pytest
from src.caption.exceptions import CaptionGenerationError
from src.caption.models import CaptionConfiguration, CaptionRequest, CaptionStatus
from src.caption.service import CaptionService
from src.clipper.models import ClipFormat, RenderedClip
from src.transcript.models import LanguageInfo, TranscriptResult, TranscriptSegment

def _request(text: str = "one two three four five six") -> CaptionRequest:
    transcript = TranscriptResult(Path("source.mp4"), text, (TranscriptSegment(0, 0, 5, text),), LanguageInfo("en", "English", True), "fake", 0)
    clip = RenderedClip("clip", Path("output/clip.mp4"), 0, 5, ClipFormat.MP4, 5)
    return CaptionRequest(transcript, clip, CaptionConfiguration(9, 1))

def test_service_segments_text_preserves_timestamps_and_reports_progress() -> None:
    events = []; result = CaptionService(logging.getLogger("test")).generate(_request(), events.append)
    assert [segment.lines for segment in result.segments] == [("one two",), ("three",), ("four five",), ("six",)]
    assert all(segment.start_seconds == 0 and segment.end_seconds == 5 for segment in result.segments)
    assert events[-1].status is CaptionStatus.COMPLETED

def test_service_ignores_transcript_segments_outside_clip() -> None:
    request = _request(); outside = TranscriptSegment(10, 10, 11, "outside")
    transcript = type(request.transcript_result)(Path("source.mp4"), "", (outside,), LanguageInfo("en", "English", True), "fake", 0)
    result = CaptionService(logging.getLogger("test")).generate(type(request)(transcript, request.rendered_clip, request.configuration))
    assert result.segments == ()

def test_service_isolates_progress_callback_failures() -> None:
    result = CaptionService(logging.getLogger("test")).generate(_request(), lambda _: (_ for _ in ()).throw(RuntimeError("callback")))
    assert result.segments


def test_service_preserves_application_errors_and_translates_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.caption.service as service_module

    def fail_validation(*_: object) -> None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(service_module, "validate_caption_result", fail_validation)
    with pytest.raises(CaptionGenerationError) as error:
        CaptionService(logging.getLogger("test")).generate(_request())
    assert isinstance(error.value.__cause__, RuntimeError)


def test_service_handles_empty_transcript_text() -> None:
    result = CaptionService(logging.getLogger("test")).generate(_request("   "))
    assert result.segments == ()
