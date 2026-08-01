"""Dependency-injection composition root for the complete AI-Clipper service graph."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from src.analyzer.models import AnalysisConfig
from src.analyzer.providers.gemini_provider import GeminiAnalysisProvider, GeminiClient
from src.analyzer.providers.factory import AnalysisProviderFactory
from src.analyzer.providers.openai_provider import OpenAIAnalysisProvider, OpenAIClient
from src.analyzer.service import AnalyzerService
from src.application.models import ApplicationRequest
from src.application.service import ApplicationService
from src.caption.service import CaptionService
from src.clipper.backends.factory import ClipRenderingBackendFactory
from src.clipper.backends.ffmpeg_backend import CommandRunner, FFmpegClipRenderingBackend
from src.clipper.models import ClipConfiguration
from src.clipper.service import ClipperService
from src.config.models import ApplicationSettings
from src.config.service import ConfigurationService
from src.core.config import ApplicationConfig
from src.downloader.models import DownloadConfig
from src.downloader.service import VideoDownloader
from src.gui.models import GenerationFormData
from src.pipeline.models import PipelineRequest
from src.pipeline.service import PipelineService
from src.transcript.backends.faster_whisper import FasterWhisperBackend, ModelFactory
from src.transcript.backends.factory import TranscriptionBackendFactory
from src.transcript.models import TranscriptConfig
from src.transcript.service import TranscriptService


RequestFactory = Callable[[GenerationFormData], ApplicationRequest]


@dataclass(frozen=True, slots=True)
class RequestDefaults:
    """Immutable request settings supplied by the application composition root.

    Attributes:
        download_config: Defaults for each source-media download.
        transcript_config: Defaults for each transcript request.
        analysis_config: Defaults for each transcript analysis request.
    """

    download_config: DownloadConfig
    transcript_config: TranscriptConfig
    analysis_config: AnalysisConfig


@dataclass(frozen=True, slots=True)
class ServiceGraph:
    """Immutable references to services assembled during application startup.

    CaptionService is retained independently until a future Pipeline revision
    adds caption generation as an explicit stage.
    """

    configuration_service: ConfigurationService
    downloader_service: VideoDownloader
    transcript_service: TranscriptService
    analyzer_service: AnalyzerService
    clipper_service: ClipperService
    caption_service: CaptionService
    pipeline_service: PipelineService
    application_service: ApplicationService
    request_factory: RequestFactory


class ServiceFactory:
    """Construct concrete adapters and service boundaries without executing them."""

    def __init__(
        self,
        application_config: ApplicationConfig,
        settings: ApplicationSettings,
        logger: logging.Logger,
        request_defaults: RequestDefaults,
        openai_client: OpenAIClient,
        gemini_client: GeminiClient,
        ffmpeg_executable: Path,
        *,
        faster_whisper_model_factory: ModelFactory | None = None,
        ffmpeg_command_runner: CommandRunner | None = None,
        analyzer_model_name: str = "gpt-4.1-mini",
        gemini_model_name: str = "gemini-2.5-flash",
        provider_timeout_seconds: float = 60.0,
        ffmpeg_timeout_seconds: float = 300.0,
    ) -> None:
        """Store every dependency required to assemble the application graph.

        All provider clients and executable paths are injected, so construction
        never loads secrets, starts providers, or probes FFmpeg.
        """
        self._application_config = application_config
        self._settings = settings
        self._logger = logger
        self._request_defaults = request_defaults
        self._openai_client = openai_client
        self._gemini_client = gemini_client
        self._ffmpeg_executable = ffmpeg_executable
        self._faster_whisper_model_factory = faster_whisper_model_factory
        self._ffmpeg_command_runner = ffmpeg_command_runner
        self._analyzer_model_name = analyzer_model_name
        self._gemini_model_name = gemini_model_name
        self._provider_timeout_seconds = provider_timeout_seconds
        self._ffmpeg_timeout_seconds = ffmpeg_timeout_seconds

    def build(self) -> ServiceGraph:
        """Construct and return the complete service graph without running work."""
        configuration_service = ConfigurationService(self._settings)
        transcript_factory = TranscriptionBackendFactory(
            {"faster-whisper": self._create_faster_whisper_backend},
            self._settings.preferred_transcript_backend,
        )
        analyzer_factory = AnalysisProviderFactory(
            {"openai": self._create_openai_provider, "gemini": self._create_gemini_provider},
            self._settings.preferred_analyzer_provider,
        )
        clipper_factory = ClipRenderingBackendFactory({"ffmpeg": self._create_ffmpeg_backend}, "ffmpeg")
        downloader_service = VideoDownloader(self._application_config, self._logger)
        transcript_service = TranscriptService(self._application_config, self._logger, transcript_factory)
        analyzer_service = AnalyzerService(self._application_config, self._logger, analyzer_factory)
        clipper_service = ClipperService(self._application_config, self._logger, clipper_factory)
        caption_service = CaptionService(self._logger)
        pipeline_service = PipelineService(
            downloader_service,
            transcript_service,
            analyzer_service,
            clipper_service,
            self._logger,
        )
        application_service = ApplicationService(pipeline_service, self._logger)
        return ServiceGraph(
            configuration_service,
            downloader_service,
            transcript_service,
            analyzer_service,
            clipper_service,
            caption_service,
            pipeline_service,
            application_service,
            self.create_request_factory(),
        )

    def create_request_factory(self) -> RequestFactory:
        """Create the GUI request adapter from immutable injected defaults."""
        def create_request(form_data: GenerationFormData) -> ApplicationRequest:
            """Convert immutable GUI form data into an immutable application request."""
            output_directory = form_data.output_directory or self._settings.default_output_directory
            pipeline_request = PipelineRequest(
                source_url=form_data.source_url,
                download_config=replace(
                    self._request_defaults.download_config,
                    output_directory=output_directory,
                ),
                transcript_config=self._request_defaults.transcript_config,
                analysis_config=self._request_defaults.analysis_config,
                clip_configuration=ClipConfiguration(output_directory),
                transcription_backend_name=self._settings.preferred_transcript_backend,
                analyzer_name=self._settings.preferred_analyzer_provider,
            )
            return ApplicationRequest(pipeline_request)

        return create_request

    def _create_faster_whisper_backend(self) -> FasterWhisperBackend:
        """Construct the lazily loaded transcription adapter."""
        return FasterWhisperBackend(self._logger, self._faster_whisper_model_factory)

    def _create_openai_provider(self) -> OpenAIAnalysisProvider:
        """Construct the injected-client OpenAI analysis adapter."""
        return OpenAIAnalysisProvider(
            self._openai_client,
            self._logger,
            self._analyzer_model_name,
            self._provider_timeout_seconds,
        )

    def _create_gemini_provider(self) -> GeminiAnalysisProvider:
        """Construct the injected-client Gemini analysis adapter."""
        return GeminiAnalysisProvider(
            self._gemini_client,
            self._logger,
            self._gemini_model_name,
            self._provider_timeout_seconds,
        )

    def _create_ffmpeg_backend(self) -> FFmpegClipRenderingBackend:
        """Construct the non-executing FFmpeg rendering adapter."""
        if self._ffmpeg_command_runner is None:
            return FFmpegClipRenderingBackend(
                self._ffmpeg_executable,
                self._logger,
                self._ffmpeg_timeout_seconds,
            )
        return FFmpegClipRenderingBackend(
            self._ffmpeg_executable,
            self._logger,
            self._ffmpeg_timeout_seconds,
            self._ffmpeg_command_runner,
        )
