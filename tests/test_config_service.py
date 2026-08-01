"""In-memory tests for immutable configuration defaults."""

from pathlib import Path

import pytest

from src.config.models import ApplicationSettings, Theme
from src.config.service import ConfigurationService


def _settings() -> ApplicationSettings:
    """Create a complete in-memory settings value without secret loading."""
    return ApplicationSettings(
        openai_api_key=None,
        gemini_api_key=None,
        default_output_directory=Path("output"),
        preferred_analyzer_provider="openai",
        preferred_transcript_backend="faster-whisper",
        theme=Theme.SYSTEM,
    )


def test_configuration_service_returns_injected_defaults_without_io() -> None:
    """Default loading returns the original immutable in-memory settings value."""
    settings = _settings()
    assert ConfigurationService(settings).load_defaults() is settings


def test_application_settings_are_immutable_and_themes_are_explicit() -> None:
    """Settings cannot be changed after construction and expose all theme choices."""
    settings = _settings()
    with pytest.raises(AttributeError):
        settings.theme = Theme.DARK
    assert {theme.value for theme in Theme} == {"light", "dark", "system"}


def test_configuration_service_rejects_non_settings_defaults() -> None:
    """Dependency injection rejects invalid configuration collaborators immediately."""
    with pytest.raises(TypeError):
        ConfigurationService(object())  # type: ignore[arg-type]
