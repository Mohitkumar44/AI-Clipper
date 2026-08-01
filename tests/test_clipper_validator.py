"""Tests for pure Clip Cutter validation."""
from pathlib import Path
import pytest
from src.clipper import validator
from src.clipper.exceptions import InvalidClipRequestError, InvalidTimestampError, OutputWriteError, UnsupportedFormatError
from src.clipper.models import ClipCandidate, ClipConfiguration, ClipFormat, RenderedClip
from src.core.config import ApplicationConfig
from src.core.paths import ProjectPaths
from src.analyzer.models import AnalyzerResult
from src.downloader.models import DownloadResult, VideoMetadata
from src.transcript.models import LanguageInfo, TranscriptResult

def _root() -> Path: return Path.cwd() / "project"
def _app() -> ApplicationConfig: return ApplicationConfig(ProjectPaths(_root()))
def _config() -> ClipConfiguration: return ClipConfiguration(_root() / "output")
def _candidate(identifier: str = "candidate-1", end: float = 30.0) -> ClipCandidate: return ClipCandidate(identifier, 0.0, end, 90.0, "Hook")

def test_configuration_candidate_and_output_path_validation() -> None:
    config, app = _config(), _app()
    assert validator.validate_clip_configuration(config, app) is config
    assert validator.validate_clip_candidate(_candidate()).candidate_id == "candidate-1"
    assert validator.validate_output_path(_root() / "output/clip.mp4", config, app).suffix == ".mp4"

@pytest.mark.parametrize("start,end", [(-1, 1), (1, 1), (2, 1)])
def test_timestamp_validation_rejects_invalid_ranges(start: float, end: float) -> None:
    with pytest.raises(InvalidTimestampError): validator.validate_timestamp_range(start, end)

def test_validator_rejects_unsafe_configuration_and_paths() -> None:
    app = _app()
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_configuration(ClipConfiguration(Path("outside")), app)
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_candidate(ClipCandidate("", 0, 30, 90, "Hook"))
    with pytest.raises(OutputWriteError): validator.validate_output_path(Path("../clip.mp4"), _config(), app)
    with pytest.raises(UnsupportedFormatError): validator.validate_output_path(_root() / "output/clip.webm", _config(), app)

def test_rendered_clip_consistency_validation() -> None:
    rendered = RenderedClip("candidate-1", _root() / "output/clip.mp4", 0, 30, ClipFormat.MP4, 30)
    assert validator.validate_rendered_clip(rendered, _config(), _app()) is rendered
    with pytest.raises(UnsupportedFormatError): validator.validate_rendered_clip(RenderedClip("candidate-1", _root() / "output/clip.mp4", 0, 30, ClipFormat.WEBM, 30), _config(), _app())

def test_full_request_duplicate_candidates_and_configuration_errors() -> None:
    metadata = VideoMetadata("id", "title", 60, None, "url", None)
    download = DownloadResult(Path("source.mp4"), metadata, False)
    transcript = TranscriptResult(Path("source.mp4"), "text", (), LanguageInfo("en", "English", True), "fake", 0)
    analysis = AnalyzerResult(Path("source.mp4"), (), (), "fake", 0)
    candidate = _candidate()
    from src.clipper.models import ClipRequest
    request = ClipRequest(download, transcript, analysis, (candidate, candidate), _config())
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_request(request, _app())
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_configuration(ClipConfiguration(_root() / "output", video_codec="bad codec"), _app())
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_configuration(ClipConfiguration(_root() / "output", overwrite="yes"), _app())  # type: ignore[arg-type]

def test_validator_rejects_invalid_model_types_and_rendered_metadata() -> None:
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_candidate("bad")  # type: ignore[arg-type]
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_candidate(ClipCandidate("candidate-1", 0, 30, -1, "Hook"))
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_candidate(ClipCandidate("candidate-1", 0, 30, 80, ""))
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_configuration("bad", _app())  # type: ignore[arg-type]
    with pytest.raises(OutputWriteError): validator.validate_output_path("bad", _config(), _app())  # type: ignore[arg-type]
    invalid_duration = RenderedClip("candidate-1", _root() / "output/clip.mp4", 0, 30, ClipFormat.MP4, 0)
    with pytest.raises(InvalidClipRequestError): validator.validate_rendered_clip(invalid_duration, _config(), _app())

def test_validator_covers_request_and_filename_boundary_failures() -> None:
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_request("bad", _app())  # type: ignore[arg-type]
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_configuration(_config(), "bad")  # type: ignore[arg-type]
    with pytest.raises(UnsupportedFormatError): validator.validate_clip_configuration(ClipConfiguration(_root() / "output", output_format="mp4"), _app())  # type: ignore[arg-type]
    with pytest.raises(InvalidClipRequestError): validator.validate_clip_configuration(ClipConfiguration(_root() / "output", include_audio="yes"), _app())  # type: ignore[arg-type]
    for name in ("bad:name.mp4", "CON.mp4", "clip. "):
        with pytest.raises(OutputWriteError): validator.validate_output_path(_root() / "output" / name, _config(), _app())
