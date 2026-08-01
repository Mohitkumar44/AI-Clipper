"""Tests for provider-neutral AnalyzerService orchestration."""
import logging
from pathlib import Path
import pytest
import src.analyzer.service as service_module
from src.analyzer.exceptions import AnalysisFailedError
from src.analyzer.models import AnalysisConfig, AnalyzerRequest, AnalyzerResult
from src.analyzer.providers.base import AnalysisProvider
from src.analyzer.providers.factory import AnalysisProviderFactory
from src.analyzer.service import AnalyzerService
from src.core.config import ApplicationConfig
from src.core.paths import ProjectPaths
from src.transcript.models import LanguageInfo, TranscriptResult

class RecordingProvider(AnalysisProvider):
    def __init__(self, fail: bool = False) -> None: self.fail, self.requests = fail, []
    def analyze(self, request: AnalyzerRequest, progress_callback=None) -> AnalyzerResult:
        self.requests.append(request)
        if self.fail: raise RuntimeError("network")
        return AnalyzerResult(request.source_path, (), (), "recording", 0.0)
    def provider_name(self) -> str: return "recording"
    def supported_models(self) -> tuple[str, ...]: return ("fake",)
    def supports_language(self, language_code: str) -> bool: return True
    def health_check(self) -> bool: return True

def _request() -> AnalyzerRequest:
    transcript = TranscriptResult(Path("video.mp4"), "Insight", (), LanguageInfo("en", "English", True), "fake", 0.0)
    return AnalyzerRequest(Path("video.mp4"), transcript, AnalysisConfig())
def _service(provider: RecordingProvider) -> AnalyzerService:
    factory = AnalysisProviderFactory({"recording": lambda: provider}, "recording")
    return AnalyzerService(ApplicationConfig(ProjectPaths(Path("project"))), logging.getLogger("test"), factory)

def test_service_validates_selects_and_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = RecordingProvider(); service = _service(provider)
    monkeypatch.setattr(service_module, "validate_analyzer_request", lambda value: value)
    monkeypatch.setattr(service_module, "validate_analyzer_result", lambda value, config: value)
    result = service.analyze(_request())
    assert result.analyzer_name == "recording" and len(provider.requests) == 1

def test_service_translates_unexpected_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "validate_analyzer_request", lambda value: value)
    with pytest.raises(AnalysisFailedError): _service(RecordingProvider(True)).analyze(_request())
