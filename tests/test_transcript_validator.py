"""Tests for pure transcript validation utilities."""

from pathlib import Path

import pytest

from src.transcript.exceptions import (
    InvalidTranscriptRequestError,
    MediaFileNotFoundError,
    MediaFormatNotSupportedError,
    TranscriptValidationError,
    UnsupportedLanguageError,
)
from src.transcript.models import (
    LanguageInfo,
    TranscriptConfig,
    TranscriptRequest,
    TranscriptResult,
    TranscriptSegment,
)
from src.transcript import validator


def test_validate_transcript_request_uses_component_validators(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid request is returned unchanged without accessing real media."""
    request = TranscriptRequest(Path("missing.mp4"), TranscriptConfig(model_name="small"))
    monkeypatch.setattr(validator, "validate_media_path", lambda path: path)
    assert validator.validate_transcript_request(request) is request


@pytest.mark.parametrize("media_path", [Path("missing.mp4"), Path("folder.unsupported")])
def test_validate_media_path_rejects_missing_or_unsupported_media(media_path: Path) -> None:
    """Media checks do not read or create any media content."""
    expected = MediaFormatNotSupportedError if media_path.suffix == ".unsupported" else MediaFileNotFoundError
    with pytest.raises(expected):
        validator.validate_media_path(media_path)


def test_validate_media_path_rejects_non_path_values() -> None:
    """The public path boundary requires a pathlib path instance."""
    with pytest.raises(InvalidTranscriptRequestError):
        validator.validate_media_path("video.mp4")  # type: ignore[arg-type]


def test_validate_media_path_accepts_mocked_file_and_translates_access_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filesystem metadata checks remain read-only and map OS errors safely."""
    media_path = Path("video.mp4")
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    assert validator.validate_media_path(media_path) == media_path
    monkeypatch.setattr(Path, "is_file", lambda _: (_ for _ in ()).throw(OSError("denied")))
    with pytest.raises(MediaFileNotFoundError):
        validator.validate_media_path(media_path)


@pytest.mark.parametrize("language_code", ["en", "pt-br", "hin"])
def test_validate_language_code_accepts_iso_style_codes(language_code: str) -> None:
    """Portable language identifiers pass without backend lookups."""
    assert validator.validate_language_code(language_code) == language_code


@pytest.mark.parametrize("language_code", ["English", "e", "en_US", ""])
def test_validate_language_code_rejects_invalid_codes(language_code: str) -> None:
    """Malformed codes expose only transcript exceptions."""
    with pytest.raises(UnsupportedLanguageError):
        validator.validate_language_code(language_code)


def test_optional_language_and_backend_names_are_allowed() -> None:
    """Automatic language detection and configured default backend are valid."""
    assert validator.validate_language_code(None) is None
    assert validator.validate_backend_name(None) is None


def test_validate_transcript_config_rejects_blank_model_name() -> None:
    """Incomplete configuration is rejected before model work starts."""
    with pytest.raises(InvalidTranscriptRequestError):
        validator.validate_transcript_config(TranscriptConfig(model_name=""))


@pytest.mark.parametrize(
    "config",
    [
        TranscriptConfig(model_name="small", device=""),
        TranscriptConfig(model_name="small", compute_type=""),
        TranscriptConfig(model_name="small", initial_prompt=1),  # type: ignore[arg-type]
    ],
)
def test_validate_transcript_config_rejects_invalid_settings(config: TranscriptConfig) -> None:
    """Every backend-independent configuration field is validated."""
    with pytest.raises(InvalidTranscriptRequestError):
        validator.validate_transcript_config(config)


@pytest.mark.parametrize("backend_name", ["faster_whisper", "azure-speech"])
def test_validate_backend_name_accepts_portable_names(backend_name: str) -> None:
    """Backend names are implementation-independent identifiers."""
    assert validator.validate_backend_name(backend_name) == backend_name


@pytest.mark.parametrize("backend_name", ["FasterWhisper", "1backend", "backend name"])
def test_validate_backend_name_rejects_invalid_names(backend_name: str) -> None:
    """Malformed backend identifiers use application exceptions."""
    with pytest.raises(InvalidTranscriptRequestError):
        validator.validate_backend_name(backend_name)


def test_validate_transcript_result_rejects_overlapping_segments() -> None:
    """Segments must be chronologically safe for downstream clip analysis."""
    result = _result(
        (
            TranscriptSegment(0, 0.0, 2.0, "First"),
            TranscriptSegment(1, 1.0, 3.0, "Second"),
        )
    )
    with pytest.raises(TranscriptValidationError):
        validator.validate_transcript_result(result)


def test_validate_transcript_result_accepts_ordered_segments() -> None:
    """A well-formed provider result is returned without mutation."""
    result = _result((TranscriptSegment(0, 0.0, 2.0, "First"),))
    assert validator.validate_transcript_result(result) is result


@pytest.mark.parametrize(
    "segments",
    [
        (TranscriptSegment(1, 0.0, 1.0, "First"), TranscriptSegment(0, 1.0, 2.0, "Second")),
        (TranscriptSegment(0, 2.0, 1.0, "Reversed"),),
        (TranscriptSegment(0, 0.0, 1.0, ""),),
    ],
)
def test_validate_transcript_result_rejects_invalid_segment_content(
    segments: tuple[TranscriptSegment, ...],
) -> None:
    """Ordering, timestamps, and text are required for AI-analysis safety."""
    with pytest.raises(TranscriptValidationError):
        validator.validate_transcript_result(_result(segments))


@pytest.mark.parametrize(
    "result",
    [
        "not-a-result",
        TranscriptResult(
            source_path="video.mp4",  # type: ignore[arg-type]
            full_text="",
            segments=(),
            language=LanguageInfo("en", "English", detected=True),
            backend_name="fake",
            processing_time_seconds=0.0,
        ),
        TranscriptResult(
            source_path=Path("video.mp4"),
            full_text="",
            segments=(),
            language=LanguageInfo("bad", "English", detected=True),
            backend_name="fake",
            processing_time_seconds=-1.0,
        ),
    ],
)
def test_validate_transcript_result_rejects_invalid_result_fields(result: object) -> None:
    """Provider results cannot bypass core path, timing, or language invariants."""
    with pytest.raises(TranscriptValidationError):
        validator.validate_transcript_result(result)  # type: ignore[arg-type]


def _result(segments: tuple[TranscriptSegment, ...]) -> TranscriptResult:
    """Build a valid result shell for transcript-validation tests."""
    return TranscriptResult(
        source_path=Path("video.mp4"),
        full_text=" ".join(segment.text for segment in segments),
        segments=segments,
        language=LanguageInfo("en", "English", detected=True),
        backend_name="fake",
        processing_time_seconds=1.0,
    )
