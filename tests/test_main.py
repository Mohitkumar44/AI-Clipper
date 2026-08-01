"""Headless tests for executable application bootstrap and composition wiring."""

import importlib
import sys
import types
from pathlib import Path


def _install_startup_stubs() -> None:
    """Install in-memory Qt and window modules before importing the entry point."""
    package = types.ModuleType("PySide6")
    widgets = types.ModuleType("PySide6.QtWidgets")

    class QApplication:
        def __init__(self, arguments): self.arguments = arguments
        def exec(self) -> int: return 0

    window_module = types.ModuleType("src.gui.main_window")
    class MainWindow:
        pass
    window_module.MainWindow = MainWindow
    window_module.RequestFactory = object
    widgets.QApplication = QApplication
    sys.modules.update({
        "PySide6": package,
        "PySide6.QtWidgets": widgets,
        "src.gui.main_window": window_module,
    })


_install_startup_stubs()
main_module = importlib.import_module("src.main")


class FakeLogger:
    """In-memory structured logger recording startup events."""
    def __init__(self) -> None: self.events = []
    def info(self, message: str, **kwargs: object) -> None: self.events.append((message, kwargs))


class FakeApplicationConfig:
    """Minimal immutable-shaped configuration without filesystem interaction."""
    logs_directory = Path("logs")
    output_directory = Path("output")
    downloads_directory = Path("downloads")


class FakeServiceFactory:
    """Composition-factory fake recording dependencies without constructing services."""
    captured_args = None
    def __init__(self, *args: object) -> None: type(self).captured_args = args
    def build(self) -> object:
        return types.SimpleNamespace(
            application_service="application-service",
            request_factory=lambda _: "application-request",
        )


class FakeQtApplication:
    """Qt application fake that never opens a native GUI."""
    def __init__(self, arguments: object) -> None: self.arguments, self.executed = arguments, False
    def exec(self) -> int: self.executed = True; return 17


class FakeWindow:
    """Window fake verifying injected service and request factory startup wiring."""
    def __init__(self) -> None: self.shown = False
    def show(self) -> None: self.shown = True


def test_build_service_graph_delegates_all_service_construction_to_service_factory() -> None:
    """Bootstrap provides immutable defaults while ServiceFactory owns all wiring."""
    logger = FakeLogger()
    graph = main_module.build_service_graph(FakeApplicationConfig(), logger, FakeServiceFactory)  # type: ignore[arg-type]
    settings = FakeServiceFactory.captured_args[1]
    defaults = FakeServiceFactory.captured_args[3]
    assert graph.application_service == "application-service"
    assert settings.default_output_directory == Path("output")
    assert defaults.download_config.output_directory == Path("downloads")
    assert settings.openai_api_key is None and settings.gemini_api_key is None


def test_main_initializes_logging_composition_gui_and_event_loop_with_injected_dependencies() -> None:
    """Startup performs composition only and never launches a real GUI or workflow."""
    logger, configured_directories, captured = FakeLogger(), [], {}

    def create_qt(arguments: object) -> FakeQtApplication:
        captured["qt"] = FakeQtApplication(arguments)
        return captured["qt"]

    def create_window(application_service: object, request_factory: object) -> FakeWindow:
        captured["dependencies"] = (application_service, request_factory)
        captured["window"] = FakeWindow()
        return captured["window"]

    exit_code = main_module.main(
        ["ai-clipper"],
        application_config_factory=FakeApplicationConfig,
        logging_configurer=configured_directories.append,
        logger_factory=lambda _: logger,
        service_factory_constructor=FakeServiceFactory,
        qt_application_factory=create_qt,
        window_factory=create_window,
    )

    assert exit_code == 17
    assert configured_directories == [Path("logs")]
    assert captured["qt"].arguments == ("ai-clipper",)
    assert captured["qt"].executed and captured["window"].shown
    assert captured["dependencies"][0] == "application-service"
    assert logger.events[0][0] == "desktop_application_started"


def test_create_main_window_injects_application_service_and_request_factory(monkeypatch) -> None:
    """The UI composition helper injects only facade-level collaborators."""
    controller_module = types.ModuleType("src.gui.controller")
    captured = {}
    class GenerationController:
        def __init__(self, application_service: object, logger: object) -> None:
            captured["controller"] = (application_service, logger)
    controller_module.GenerationController = GenerationController
    monkeypatch.setitem(sys.modules, "src.gui.controller", controller_module)
    monkeypatch.setattr(main_module, "get_logger", lambda _: "logger")
    class Window:
        def __init__(self, controller: object, request_factory: object) -> None:
            captured["window"] = (controller, request_factory)
    monkeypatch.setattr(main_module, "MainWindow", Window)
    window = main_module.create_main_window("application-service", "request-factory")
    assert isinstance(window, Window)
    assert captured["controller"] == ("application-service", "logger")
    assert captured["window"][1] == "request-factory"
