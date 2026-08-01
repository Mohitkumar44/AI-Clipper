"""In-memory tests for composition-root dependency wiring."""

import logging
from pathlib import Path

from src.analyzer.models import AnalysisConfig
from src.application.service import ApplicationService
from src.composition.service_factory import RequestDefaults, ServiceFactory
from src.config.models import ApplicationSettings, Theme
from src.core.config import ApplicationConfig
from src.downloader.models import DownloadConfig
from src.gui.models import GenerationFormData
from src.transcript.models import TranscriptConfig


class FakeOpenAIClient:
    """In-memory OpenAI-client substitute that never performs a request."""


class FakeGeminiClient:
    """In-memory Gemini-client substitute that never performs a request."""


def _factory() -> ServiceFactory:
    """Build a composition factory using only inert in-memory collaborators."""
    application_config = ApplicationConfig.default()
    settings = ApplicationSettings(
        None,
        None,
        application_config.output_directory,
        "openai",
        "faster-whisper",
        Theme.SYSTEM,
    )
    defaults = RequestDefaults(
        DownloadConfig(application_config.downloads_directory),
        TranscriptConfig("small"),
        AnalysisConfig(),
    )
    return ServiceFactory(
        application_config,
        settings,
        logging.getLogger("test.composition"),
        defaults,
        FakeOpenAIClient(),  # type: ignore[arg-type]
        FakeGeminiClient(),  # type: ignore[arg-type]
        Path("ffmpeg"),
    )


def test_factory_builds_the_complete_service_graph_without_executing_it() -> None:
    """All services are wired as inert objects and ApplicationService is exposed."""
    graph = _factory().build()
    assert isinstance(graph.application_service, ApplicationService)
    assert graph.configuration_service.load_defaults().preferred_analyzer_provider == "openai"
    assert graph.pipeline_service._downloader_service is graph.downloader_service
    assert graph.pipeline_service._transcript_service is graph.transcript_service
    assert graph.pipeline_service._analyzer_service is graph.analyzer_service
    assert graph.pipeline_service._clipper_service is graph.clipper_service


def test_request_factory_creates_an_application_request_from_gui_data() -> None:
    """GUI form values are composed into immutable application request settings."""
    graph = _factory().build()
    request = graph.request_factory(GenerationFormData("https://youtu.be/abc123", Path("chosen-output")))
    pipeline_request = request.pipeline_request
    assert pipeline_request.source_url == "https://youtu.be/abc123"
    assert pipeline_request.clip_configuration.output_directory == Path("chosen-output")
    assert pipeline_request.analyzer_name == "openai"
    assert pipeline_request.transcription_backend_name == "faster-whisper"


def test_factory_constructs_registered_adapters_lazily() -> None:
    """Registry lookups create adapters without loading models or executing tools."""
    graph = _factory().build()
    transcript_backend = graph.transcript_service._backend_factory.get_default_backend()
    analyzer_provider = graph.analyzer_service._provider_factory.get_default_provider()
    clipper_backend = graph.clipper_service._backend_factory.get_default_backend()
    assert not transcript_backend.is_model_loaded()
    assert analyzer_provider.provider_name() == "openai"
    assert clipper_backend.backend_name() == "ffmpeg"
