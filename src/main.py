"""Composition root and desktop entry point for the AI-Clipper application."""

from __future__ import annotations

import sys
from collections.abc import Callable

from PySide6.QtWidgets import QApplication

from src.application.service import ApplicationService
from src.config.models import ApplicationSettings, Theme
from src.config.service import ConfigurationService
from src.core.config import ApplicationConfig
from src.core.logger import configure_logging, get_logger
from src.gui.controller import GenerationController
from src.gui.main_window import MainWindow, RequestFactory


ApplicationServiceFactory = Callable[[ApplicationSettings], ApplicationService]


def create_main_window(
    application_service: ApplicationService,
    request_factory: RequestFactory,
) -> MainWindow:
    """Assemble the GUI with explicitly injected application collaborators.

    Args:
        application_service: Fully composed high-level application service.
        request_factory: Adapter that creates immutable application requests from UI values.

    Returns:
        Configured main window ready to be shown by the Qt event loop.
    """
    logger = get_logger(__name__)
    controller = GenerationController(application_service, logger)
    return MainWindow(controller, request_factory)


def main(
    application_service_factory: ApplicationServiceFactory,
    request_factory: RequestFactory,
) -> int:
    """Initialize runtime infrastructure and start the desktop event loop.

    Service construction remains injectable so this composition root never owns
    provider credentials, external clients, or business workflow decisions.

    Args:
        application_service_factory: Factory that assembles the application service graph.
        request_factory: Adapter that builds application requests from GUI form values.

    Returns:
        Qt process exit code.
    """
    core_configuration = ApplicationConfig.default()
    configure_logging(core_configuration.logs_directory)
    logger = get_logger(__name__)
    configuration_service = ConfigurationService(
        ApplicationSettings(
            openai_api_key=None,
            gemini_api_key=None,
            default_output_directory=core_configuration.output_directory,
            preferred_analyzer_provider="openai",
            preferred_transcript_backend="faster-whisper",
            theme=Theme.SYSTEM,
        )
    )
    application = QApplication(sys.argv)
    application_service = application_service_factory(configuration_service.load_defaults())
    window = create_main_window(application_service, request_factory)
    window.show()
    logger.info("desktop_application_started", extra={"event": "desktop_application_started"})
    return application.exec()


if __name__ == "__main__":
    raise SystemExit("Compose ApplicationService and RequestFactory before invoking main().")
