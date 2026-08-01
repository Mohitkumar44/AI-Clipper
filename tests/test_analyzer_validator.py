"""Tests for pure analyzer validation."""
from pathlib import Path
import pytest
from src.analyzer import validator
from src.analyzer.exceptions import InvalidAnalysisRequestError, InvalidAnalysisResultError
from src.analyzer.models import AnalysisConfig, AnalyzerRequest, AnalyzerResult, ClipCandidate, ViralMoment, ViralMomentType
from src.transcript.models import LanguageInfo, TranscriptResult

def _transcript(text: str = "Insight") -> TranscriptResult:
    return TranscriptResult(Path("video.mp4"), text, (), LanguageInfo("en", "English", True), "fake", 0.0)
def _candidate(identifier: str = "candidate-1", score: float = 90.0, end: float = 30.0) -> ClipCandidate:
    return ClipCandidate(identifier, 0.0, end, score, "Hook")
def _moment(identifier: str = "moment-1") -> ViralMoment:
    return ViralMoment(identifier, ViralMomentType.HOOK, 0.0, 30.0, 80.0, "Opening")
def _result(candidates: tuple[ClipCandidate, ...] = ()) -> AnalyzerResult:
    return AnalyzerResult(Path("video.mp4"), candidates, (_moment(),), "fake", 0.0)

def test_request_and_result_validation_accept_valid_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    request = AnalyzerRequest(Path("video.mp4"), _transcript(), AnalysisConfig())
    assert validator.validate_analyzer_request(request) is request
    assert validator.validate_analyzer_result(_result((_candidate(),)))

@pytest.mark.parametrize("config", [AnalysisConfig(maximum_candidates=0), AnalysisConfig(minimum_clip_duration_seconds=0), AnalysisConfig(minimum_clip_duration_seconds=60, maximum_clip_duration_seconds=15), AnalysisConfig(target_language_code="English"), AnalysisConfig(custom_instructions="x" * 4001)])
def test_config_rejects_invalid_limits(config: AnalysisConfig) -> None:
    with pytest.raises(InvalidAnalysisRequestError):
        validator.validate_analysis_config(config)

@pytest.mark.parametrize("candidates", [(_candidate("candidate-1"), _candidate("candidate-1", 80)), (_candidate("candidate-1", 80), _candidate("candidate-2", 90)), (_candidate(score=101),)])
def test_result_rejects_duplicate_unordered_and_invalid_scores(monkeypatch: pytest.MonkeyPatch, candidates: tuple[ClipCandidate, ...]) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    with pytest.raises(InvalidAnalysisResultError):
        validator.validate_analyzer_result(_result(candidates))

def test_candidate_and_moment_validation_reject_invalid_ranges() -> None:
    with pytest.raises(InvalidAnalysisResultError):
        validator.validate_clip_candidate(_candidate(end=5), AnalysisConfig())
    with pytest.raises(InvalidAnalysisResultError):
        validator.validate_viral_moment(ViralMoment("moment-1", ViralMomentType.HOOK, 2.0, 1.0, 80.0, "Bad"))

def test_request_rejects_missing_source_or_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(InvalidAnalysisRequestError):
        validator.validate_analyzer_request(AnalyzerRequest(Path("missing.mp4"), _transcript(), AnalysisConfig()))
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    with pytest.raises(InvalidAnalysisRequestError):
        validator.validate_analyzer_request(AnalyzerRequest(Path("video.mp4"), _transcript(""), AnalysisConfig()))

def test_validator_rejects_invalid_types_and_result_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    with pytest.raises(InvalidAnalysisRequestError): validator.validate_analysis_config("bad")  # type: ignore[arg-type]
    with pytest.raises(InvalidAnalysisResultError): validator.validate_analyzer_result("bad")  # type: ignore[arg-type]
    over_limit = tuple(_candidate(f"candidate-{index}") for index in range(2))
    with pytest.raises(InvalidAnalysisResultError): validator.validate_analyzer_result(_result(over_limit), AnalysisConfig(maximum_candidates=1))
    with pytest.raises(InvalidAnalysisResultError): validator.validate_viral_moment(ViralMoment("moment-1", ViralMomentType.HOOK, 0, 30, -1, "Bad"))

def test_validator_rejects_invalid_request_result_and_candidate_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _: True)
    with pytest.raises(InvalidAnalysisRequestError): validator.validate_analyzer_request("bad")  # type: ignore[arg-type]
    with pytest.raises(InvalidAnalysisRequestError): validator.validate_analysis_config(AnalysisConfig(include_transcript_excerpt="yes"))  # type: ignore[arg-type]
    with pytest.raises(InvalidAnalysisResultError): validator.validate_clip_candidate(ClipCandidate("Bad Id", 0, 30, 80, "Hook"), AnalysisConfig())
    with pytest.raises(InvalidAnalysisResultError): validator.validate_clip_candidate(ClipCandidate("candidate-1", 0, 30, 80, ""), AnalysisConfig())
    with pytest.raises(InvalidAnalysisResultError): validator.validate_analyzer_result(AnalyzerResult(Path("video.mp4"), (), (), "", -1))
