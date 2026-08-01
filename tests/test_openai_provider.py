"""Tests for the injected OpenAI analysis adapter."""
import json
import logging
from pathlib import Path
import pytest
import src.analyzer.providers.openai_provider as module
from src.analyzer.exceptions import AnalyzerConfigurationError, InvalidAnalysisResultError, ProviderCommunicationError, RateLimitExceededError
from src.analyzer.models import AnalysisConfig, AnalyzerRequest, AnalysisStatus
from src.analyzer.providers.openai_provider import OpenAIAnalysisProvider
from src.transcript.models import LanguageInfo, TranscriptResult

class Response:
    def __init__(self, text: str) -> None: self.output_text = text
class Responses:
    def __init__(self, response: object = None, error: Exception | None = None) -> None: self.response, self.error, self.calls = response, error, []
    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error: raise self.error
        return self.response
class Client:
    def __init__(self, responses: Responses) -> None: self.responses = responses
class RateError(Exception): status_code = 429
def _request() -> AnalyzerRequest:
    transcript = TranscriptResult(Path("video.mp4"), "Insight", (), LanguageInfo("en", "English", True), "fake", 0.0)
    return AnalyzerRequest(Path("video.mp4"), transcript, AnalysisConfig())
def _payload() -> str:
    return json.dumps({"candidates":[{"candidate_id":"candidate-1","start_seconds":0,"end_seconds":30,"score":90,"reason":"Hook"}],"viral_moments":[{"moment_id":"moment-1","moment_type":"hook","start_seconds":0,"end_seconds":30,"score":80,"explanation":"Opening"}]})

def test_openai_provider_parses_response_progress_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = Responses(Response(_payload())); provider = OpenAIAnalysisProvider(Client(responses), logging.getLogger("test"), "model", 12)
    monkeypatch.setattr(module, "validate_analyzer_request", lambda value: value)
    monkeypatch.setattr(module, "validate_analyzer_result", lambda value, config: value)
    events = []; result = provider.analyze(_request(), events.append)
    assert result.candidates[0].candidate_id == "candidate-1"
    assert responses.calls[0]["timeout"] == 12.0
    assert [event.status for event in events] == [AnalysisStatus.PREPARING, AnalysisStatus.ANALYZING, AnalysisStatus.COMPLETED]
    assert provider.health_check() is True and provider.supported_models() == ("model",)

def test_openai_provider_translates_rate_and_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "validate_analyzer_request", lambda value: value)
    rate_provider = OpenAIAnalysisProvider(Client(Responses(error=RateError("rate limit"))), logging.getLogger("test"), "model", 1)
    with pytest.raises(RateLimitExceededError): rate_provider.analyze(_request())
    invalid_provider = OpenAIAnalysisProvider(Client(Responses(Response("not-json"))), logging.getLogger("test"), "model", 1)
    with pytest.raises(InvalidAnalysisResultError): invalid_provider.analyze(_request())

def test_openai_configuration_callback_and_communication_behaviors(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AnalyzerConfigurationError): OpenAIAnalysisProvider(Client(Responses()), logging.getLogger("test"), "", 1)
    with pytest.raises(AnalyzerConfigurationError): OpenAIAnalysisProvider(Client(Responses()), logging.getLogger("test"), "model", 0)
    monkeypatch.setattr(module, "validate_analyzer_request", lambda value: value)
    monkeypatch.setattr(module, "validate_analyzer_result", lambda value, config: value)
    provider = OpenAIAnalysisProvider(Client(Responses(Response(_payload()))), logging.getLogger("test"), "model", 1)
    assert provider.analyze(_request(), lambda _: (_ for _ in ()).throw(RuntimeError("callback"))).analyzer_name == "openai"
    unavailable = OpenAIAnalysisProvider(Client(Responses(error=RuntimeError("network timeout"))), logging.getLogger("test"), "model", 1)
    with pytest.raises(ProviderCommunicationError): unavailable.analyze(_request())
    assert provider.supports_language("") is False

def test_openai_response_helpers_reject_malformed_provider_objects() -> None:
    with pytest.raises(InvalidAnalysisResultError): module._parse_candidate({"candidate_id": "candidate-1"})
    with pytest.raises(InvalidAnalysisResultError): module._parse_viral_moment({"moment_type": "unknown"})
    with pytest.raises(InvalidAnalysisResultError): module._optional_string(1)
    assert module._optional_string(None) is None
    assert isinstance(module._translate_provider_error(RuntimeError("unexpected")), module.AnalysisFailedError)
