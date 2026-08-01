"""Tests for analysis provider factory."""
from pathlib import Path
import pytest
from src.analyzer.exceptions import AnalysisFailedError, AnalyzerConfigurationError, InvalidAnalysisRequestError, UnsupportedAnalyzerError
from src.analyzer.models import AnalyzerRequest, AnalyzerResult
from src.analyzer.providers.base import AnalysisProvider
from src.analyzer.providers.factory import AnalysisProviderFactory

class FakeProvider(AnalysisProvider):
    def analyze(self, request: AnalyzerRequest, progress_callback=None) -> AnalyzerResult: raise NotImplementedError
    def provider_name(self) -> str: return "fake"
    def supported_models(self) -> tuple[str, ...]: return ("fake",)
    def supports_language(self, language_code: str) -> bool: return True
    def health_check(self) -> bool: return True

def test_factory_registers_selects_and_lists_providers() -> None:
    factory = AnalysisProviderFactory({"fake": FakeProvider}, "fake")
    assert factory.available_providers() == ("fake",)
    assert isinstance(factory.get_provider("fake"), FakeProvider)
    assert isinstance(factory.get_default_provider(), FakeProvider)

def test_factory_translates_invalid_unknown_and_broken_providers() -> None:
    factory = AnalysisProviderFactory()
    with pytest.raises(AnalyzerConfigurationError): factory.get_default_provider()
    with pytest.raises(UnsupportedAnalyzerError): factory.get_provider("missing")
    with pytest.raises(InvalidAnalysisRequestError): factory.register_provider("Bad Name", FakeProvider)
    factory.register_provider("broken", lambda: object())
    with pytest.raises(AnalysisFailedError): factory.get_provider("broken")
    with pytest.raises(AnalyzerConfigurationError): AnalysisProviderFactory({"fake": FakeProvider}, "missing")
    factory.register_provider("crash", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(AnalysisFailedError): factory.get_provider("crash")
