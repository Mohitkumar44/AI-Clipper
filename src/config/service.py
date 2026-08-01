"""Service exposing injected immutable application configuration defaults."""

from __future__ import annotations

from .models import ApplicationSettings


class ConfigurationService:
    """Provide in-memory defaults without persistence, I/O, or environment access."""

    def __init__(self, default_settings: ApplicationSettings) -> None:
        """Initialize the service with defaults supplied by the composition root.

        Args:
            default_settings: Immutable settings to return for this application session.

        Raises:
            TypeError: If the supplied settings are not an ApplicationSettings model.
        """
        if not isinstance(default_settings, ApplicationSettings):
            raise TypeError("default_settings must be an ApplicationSettings instance.")
        self._default_settings = default_settings

    def load_defaults(self) -> ApplicationSettings:
        """Return the injected immutable defaults without reading or writing storage.

        Returns:
            The exact immutable settings instance provided at construction time.
        """
        return self._default_settings
