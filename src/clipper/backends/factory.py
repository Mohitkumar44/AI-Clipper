"""Dependency-injected registry for clip-rendering backend implementations."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from ..exceptions import ClipRenderingError, ClipperError, InvalidClipRequestError
from .base import ClipRenderingBackend


BackendFactory = Callable[[], ClipRenderingBackend]
BACKEND_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class ClipRenderingBackendFactory:
    """Create registered rendering backends by stable application identifier."""

    def __init__(
        self,
        backend_factories: Mapping[str, BackendFactory] | None = None,
        default_backend_name: str | None = None,
    ) -> None:
        """Initialize an independent rendering-backend registry.

        Args:
            backend_factories: Optional initial mapping of names to constructors.
            default_backend_name: Optional registered backend selected by default.

        Raises:
            InvalidClipRequestError: If the configured default is not registered.
        """
        self._backend_factories: dict[str, BackendFactory] = {}
        for name, factory in (backend_factories or {}).items():
            self.register_backend(name, factory)

        if default_backend_name is not None:
            self._validate_backend_name(default_backend_name)
            if default_backend_name not in self._backend_factories:
                raise InvalidClipRequestError("The default rendering backend is not registered.")
        self._default_backend_name = default_backend_name

    def register_backend(self, name: str, factory: BackendFactory) -> None:
        """Register a rendering-backend constructor under a stable identifier.

        Args:
            name: Lowercase application identifier for the backend.
            factory: Zero-argument constructor for a rendering backend.

        Raises:
            InvalidClipRequestError: If the name or factory is invalid.
        """
        self._validate_backend_name(name)
        if not callable(factory):
            raise InvalidClipRequestError("backend factory must be callable.")
        self._backend_factories[name] = factory

    def get_backend(self, name: str) -> ClipRenderingBackend:
        """Create and return a rendering backend registered under *name*.

        Args:
            name: Lowercase backend identifier to resolve.

        Returns:
            A newly constructed rendering backend instance.

        Raises:
            InvalidClipRequestError: If the backend name is malformed or absent.
            ClipRenderingError: If construction fails or returns an incompatible object.
        """
        self._validate_backend_name(name)
        backend_factory = self._backend_factories.get(name)
        if backend_factory is None:
            raise InvalidClipRequestError("The requested rendering backend is not registered.")

        try:
            backend = backend_factory()
        except ClipperError:
            raise
        except Exception as error:
            raise ClipRenderingError("The rendering backend could not be created.") from error

        if not isinstance(backend, ClipRenderingBackend):
            raise ClipRenderingError(
                "The registered factory did not return a ClipRenderingBackend instance."
            )
        return backend

    def get_default_backend(self) -> ClipRenderingBackend:
        """Create and return the configured default rendering backend.

        Returns:
            A newly constructed default rendering backend.

        Raises:
            InvalidClipRequestError: If no default backend has been configured.
        """
        if self._default_backend_name is None:
            raise InvalidClipRequestError("No default rendering backend is configured.")
        return self.get_backend(self._default_backend_name)

    def available_backends(self) -> tuple[str, ...]:
        """Return registered backend names in deterministic alphabetical order.

        Returns:
            An immutable ordered sequence of registered backend identifiers.
        """
        return tuple(sorted(self._backend_factories))

    @staticmethod
    def _validate_backend_name(name: str) -> None:
        """Validate a portable backend identifier without backend lookups.

        Args:
            name: Identifier to validate.

        Raises:
            InvalidClipRequestError: If the identifier is malformed.
        """
        if not isinstance(name, str) or not BACKEND_NAME_PATTERN.fullmatch(name):
            raise InvalidClipRequestError("backend name must be a lowercase identifier.")
