"""Tests for immutable analyzer models."""
from pathlib import Path
import pytest
from src.analyzer.models import AnalysisConfig, AnalysisProgress, AnalysisStatus, AnalyzerRequest, AnalyzerResult, ClipCandidate, ViralMoment, ViralMomentType
from src.transcript.models import LanguageInfo, TranscriptResult

def _transcript() -> TranscriptResult:
    return TranscriptResult(Path("video.mp4"), "Insight", (), LanguageInfo("en", "English", True), "fake", 0.0)

def test_models_are_immutable_and_provider_independent() -> None:
    config = AnalysisConfig(maximum_candidates=4)
    request = AnalyzerRequest(Path("video.mp4"), _transcript(), config)
    candidate = ClipCandidate("candidate-1", 0.0, 30.0, 90.0, "Hook")
    moment = ViralMoment("moment-1", ViralMomentType.HOOK, 0.0, 30.0, 90.0, "Opening")
    result = AnalyzerResult(Path("video.mp4"), (candidate,), (moment,), "fake", 1.0)
    assert request.config.maximum_candidates == 4
    assert result.viral_moments[0].moment_type is ViralMomentType.HOOK
    with pytest.raises(AttributeError):
        config.maximum_candidates = 3  # type: ignore[misc]

def test_analysis_progress_supports_indeterminate_status() -> None:
    assert AnalysisProgress(AnalysisStatus.PREPARING).progress_percentage is None
