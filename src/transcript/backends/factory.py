"""Dependency-injected registry for transcription backend implementations."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from ..exceptions import (
    InvalidTranscriptRequestError,
    ModelNotAvailableError,
    TranscriptError,
    TranscriptionFailedError,
)
from .base import TranscriptionBackend


BackendFactory = Callable[[], TranscriptionBackend]
BACKEND_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class TranscriptionBackendFactory:
    """Create registered transcription backends by stable application name.

    The factory stores provider constructors, not pre-created provider objects.
    This keeps lifecycle management with the application composition root and
    permits test suites to inject lightweight fake backend factories.
    """

    def __init__(
        self,
        backend_factories: Mapping[str, BackendFactory] | None = None,
        default_backend_name: str | None = None,
    ) -> None:
        """Initialize an independent backend registry.

        Args:
            backend_factories: Optional initial mapping of backend names to
                constructors.
            default_backend_name: Optional registered backend used when callers
                request the default backend.
        """
        self._backend_factories: dict[str, BackendFactory] = {}
        for name, factory in (backend_factories or {}).items():
            self.register_backend(name, factory)

        if default_backend_name is not None:
            self._validate_backend_name(default_backend_name)
            if default_backend_name not in self._backend_factories:
                raise ModelNotAvailableError("The configured default backend is not registered.")
        self._default_backend_name = default_backend_name

    def register_backend(self, name: str, factory: BackendFactory) -> None:
        """Register a constructor under a stable backend identifier.

        Args:
            name: Lowercase application identifier for the backend.
            factory: Zero-argument constructor for a backend implementation.

        Raises:
            InvalidTranscriptRequestError: If the name or factory is invalid.
        """
        self._validate_backend_name(name)
        if not callable(factory):
            raise InvalidTranscriptRequestError("backend factory must be callable.")
        self._backend_factories[name] = factory

    def get_backend(self, name: str) -> TranscriptionBackend:
        """Create and return a backend instance registered under *name*.

        Raises:
            InvalidTranscriptRequestError: If *name* is malformed.
            ModelNotAvailableError: If no backend is registered under *name*.
            TranscriptionFailedError: If construction fails or returns an
                incompatible object.
        """
        self._validate_backend_name(name)
        backend_factory = self._backend_factories.get(name)
        if backend_factory is None:
            raise ModelNotAvailableError("The requested transcription backend is not registered.")

        try:
            backend = backend_factory()
        except TranscriptError:
            raise
        except Exception as error:
            raise TranscriptionFailedError("The transcription backend could not be created.") from error

        if not isinstance(backend, TranscriptionBackend):
            raise TranscriptionFailedError(
                "The registered factory did not return a TranscriptionBackend instance."
            )
        return backend

    def get_default_backend(self) -> TranscriptionBackend:
        """Create and return the configured default backend instance.

        Raises:
            ModelNotAvailableError: If a default backend has not been configured.
        """
        if self._default_backend_name is None:
            raise ModelNotAvailableError("No default transcription backend is configured.")
        return self.get_backend(self._default_backend_name)

    def available_backends(self) -> tuple[str, ...]:
        """Return registered backend names in deterministic alphabetical order."""
        return tuple(sorted(self._backend_factories))

    @staticmethod
    def _validate_backend_name(name: str) -> None:
        """Validate a portable backend identifier without provider lookups."""
        if not isinstance(name, str) or not BACKEND_NAME_PATTERN.fullmatch(name):
            raise InvalidTranscriptRequestError("backend name must be a lowercase identifier.")
