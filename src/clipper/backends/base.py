"""Abstract contract for provider-independent clip-rendering backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import (
    ClipCandidate,
    ClipConfiguration,
    ClipFormat,
    ClipRequest,
    ProgressCallback,
    RenderedClip,
)


class ClipRenderingBackend(ABC):
    """Common rendering contract implemented by every clip-cutting backend.

    Implementations may use local applications, Python media libraries, or
    remote renderers, but must expose only the stable Clip Cutter models at
    this boundary.
    """

    @abstractmethod
    def render_clip(
        self,
        request: ClipRequest,
        candidate: ClipCandidate,
        progress_callback: ProgressCallback | None = None,
    ) -> RenderedClip:
        """Render one selected candidate from a validated clip request.

        Args:
            request: Immutable request containing source and output context.
            candidate: One validated timestamp range selected for rendering.
            progress_callback: Optional receiver for normalized rendering updates.

        Returns:
            A provider-independent model describing the rendered output clip.

        Raises:
            ClipperError: If the backend cannot render the requested clip.
        """
        ...

    @abstractmethod
    def validate_backend(self, configuration: ClipConfiguration) -> None:
        """Validate that the backend can honor the supplied output configuration.

        Args:
            configuration: Immutable clip output and encoding settings.

        Raises:
            ClipperError: If the backend is unavailable or incompatible.
        """
        ...

    @abstractmethod
    def backend_name(self) -> str:
        """Return the stable application identifier for this backend.

        Returns:
            A lowercase backend identifier suitable for application selection.
        """
        ...

    @abstractmethod
    def supported_formats(self) -> frozenset[ClipFormat]:
        """Return container formats supported by this rendering backend.

        Returns:
            An immutable set of supported clip output formats.
        """
        ...
