"""Dependency-injected registry for analysis provider implementations."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from ..exceptions import (
    AnalysisFailedError,
    AnalyzerConfigurationError,
    AnalyzerError,
    InvalidAnalysisRequestError,
    UnsupportedAnalyzerError,
)
from .base import AnalysisProvider


ProviderFactory = Callable[[], AnalysisProvider]
PROVIDER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class AnalysisProviderFactory:
    """Create registered analysis providers by stable application identifier."""

    def __init__(
        self,
        provider_factories: Mapping[str, ProviderFactory] | None = None,
        default_provider_name: str | None = None,
    ) -> None:
        """Initialize an independent provider registry.

        Args:
            provider_factories: Optional initial mapping of names to constructors.
            default_provider_name: Optional registered provider used by default.

        Raises:
            AnalyzerConfigurationError: If the configured default is not registered.
        """
        self._provider_factories: dict[str, ProviderFactory] = {}
        for name, factory in (provider_factories or {}).items():
            self.register_provider(name, factory)

        if default_provider_name is not None:
            self._validate_provider_name(default_provider_name)
            if default_provider_name not in self._provider_factories:
                raise AnalyzerConfigurationError("The default provider is not registered.")
        self._default_provider_name = default_provider_name

    def register_provider(self, name: str, factory: ProviderFactory) -> None:
        """Register a provider constructor under a stable identifier.

        Args:
            name: Lowercase application identifier for the provider.
            factory: Zero-argument constructor for an analysis provider.

        Raises:
            InvalidAnalysisRequestError: If the name or factory is invalid.
        """
        self._validate_provider_name(name)
        if not callable(factory):
            raise InvalidAnalysisRequestError("provider factory must be callable.")
        self._provider_factories[name] = factory

    def get_provider(self, name: str) -> AnalysisProvider:
        """Create and return a provider instance registered under *name*.

        Args:
            name: Lowercase provider identifier to resolve.

        Returns:
            A newly constructed provider instance.

        Raises:
            InvalidAnalysisRequestError: If the provider name is malformed.
            UnsupportedAnalyzerError: If no provider is registered under *name*.
            AnalysisFailedError: If provider construction fails or is incompatible.
        """
        self._validate_provider_name(name)
        provider_factory = self._provider_factories.get(name)
        if provider_factory is None:
            raise UnsupportedAnalyzerError("The requested analysis provider is not registered.")

        try:
            provider = provider_factory()
        except AnalyzerError:
            raise
        except Exception as error:
            raise AnalysisFailedError("The analysis provider could not be created.") from error

        if not isinstance(provider, AnalysisProvider):
            raise AnalysisFailedError(
                "The registered factory did not return an AnalysisProvider instance."
            )
        return provider

    def get_default_provider(self) -> AnalysisProvider:
        """Create and return the configured default provider.

        Returns:
            A newly constructed default analysis provider.

        Raises:
            AnalyzerConfigurationError: If no default provider is configured.
        """
        if self._default_provider_name is None:
            raise AnalyzerConfigurationError("No default analysis provider is configured.")
        return self.get_provider(self._default_provider_name)

    def available_providers(self) -> tuple[str, ...]:
        """Return registered provider names in deterministic alphabetical order.

        Returns:
            An immutable ordered sequence of registered provider identifiers.
        """
        return tuple(sorted(self._provider_factories))

    @staticmethod
    def _validate_provider_name(name: str) -> None:
        """Validate a provider identifier without provider-specific lookups.

        Args:
            name: Identifier to validate.

        Raises:
            InvalidAnalysisRequestError: If the identifier is malformed.
        """
        if not isinstance(name, str) or not PROVIDER_NAME_PATTERN.fullmatch(name):
            raise InvalidAnalysisRequestError("provider name must be a lowercase identifier.")
