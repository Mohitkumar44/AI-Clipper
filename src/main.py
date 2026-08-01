"""Executable composition root for the AI-Clipper desktop application."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.composition.service_factory import RequestDefaults, ServiceFactory, ServiceGraph
from src.config.models import ApplicationSettings, Theme
from src.core.config import ApplicationConfig
from src.core.logger import configure_logging, get_logger
from src.downloader.models import DownloadConfig
from src.gui.main_window import MainWindow, RequestFactory
from src.transcript.models import TranscriptConfig
from src.analyzer.models import AnalysisConfig


ServiceFactoryConstructor = Callable[..., ServiceFactory]
WindowFactory = Callable[[object, RequestFactory], MainWindow]
QtApplicationFactory = Callable[[Sequence[str]], QApplication]


def build_service_graph(
    application_config: ApplicationConfig,
    logger: object,
    service_factory_constructor: ServiceFactoryConstructor = ServiceFactory,
) -> ServiceGraph:
    """Create the complete inert service graph through the composition root.

    Args:
        application_config: Immutable core locations and operational limits.
        logger: Structured logger shared by all constructed services.
        service_factory_constructor: Injectable concrete composition factory.

    Returns:
        Fully wired service graph. No workflow is executed during construction.
    """
    settings = ApplicationSettings(
        openai_api_key=None,
        gemini_api_key=None,
        default_output_directory=application_config.output_directory,
        preferred_analyzer_provider="openai",
        preferred_transcript_backend="faster-whisper",
        theme=Theme.SYSTEM,
    )
    request_defaults = RequestDefaults(
        download_config=DownloadConfig(application_config.downloads_directory),
        transcript_config=TranscriptConfig("small"),
        analysis_config=AnalysisConfig(),
    )
    factory = service_factory_constructor(
        application_config,
        settings,
        logger,
        request_defaults,
        object(),
        object(),
        Path("ffmpeg"),
    )
    return factory.build()


def create_main_window(application_service: object, request_factory: RequestFactory) -> MainWindow:
    """Construct the desktop window with its injected application dependencies."""
    from src.gui.controller import GenerationController

    controller = GenerationController(application_service, get_logger(__name__))
    return MainWindow(controller, request_factory)


def main(
    argv: Sequence[str] | None = None,
    *,
    application_config_factory: Callable[[], ApplicationConfig] = ApplicationConfig.default,
    logging_configurer: Callable[[Path], None] = configure_logging,
    logger_factory: Callable[[str], object] = get_logger,
    service_factory_constructor: ServiceFactoryConstructor = ServiceFactory,
    qt_application_factory: QtApplicationFactory = QApplication,
    window_factory: WindowFactory = create_main_window,
) -> int:
    """Initialize infrastructure, compose services, show the window, and enter Qt.

    Args:
        argv: Optional process arguments forwarded to QApplication.
        application_config_factory: Injectable core configuration constructor.
        logging_configurer: Injectable logging initializer.
        logger_factory: Injectable structured logger accessor.
        service_factory_constructor: Injectable service-graph composition factory.
        qt_application_factory: Injectable Qt application constructor.
        window_factory: Injectable GUI-window constructor.

    Returns:
        Exit code reported by the Qt event loop.
    """
    application_config = application_config_factory()
    logging_configurer(application_config.logs_directory)
    logger = logger_factory(__name__)
    service_graph = build_service_graph(application_config, logger, service_factory_constructor)
    application = qt_application_factory(list(argv) if argv is not None else list(sys.argv))
    window = window_factory(service_graph.application_service, service_graph.request_factory)
    window.show()
    logger.info("desktop_application_started", extra={"event": "desktop_application_started"})
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
