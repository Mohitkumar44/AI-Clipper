"""Abstract provider contract for transcript-generation backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..models import (
    TranscriptConfig,
    TranscriptProgress,
    TranscriptRequest,
    TranscriptResult,
    TranscriptTask,
)


ProgressCallback = Callable[[TranscriptProgress], None]


class TranscriptionBackend(ABC):
    """Common contract implemented by every supported transcription provider.

    Implementations may use local or remote engines, but must convert their
    provider-specific behavior into the public transcript models defined by the
    application.
    """

    @abstractmethod
    def load_model(self, config: TranscriptConfig) -> None:
        """Load or initialize resources required by the configured model.

        Args:
            config: Immutable settings identifying the requested model and
                compute configuration.

        Raises:
            TranscriptError: If the model cannot be made ready for use.
        """
        ...

    @abstractmethod
    def is_model_loaded(self) -> bool:
        """Return whether this backend currently has a usable model loaded."""
        ...

    @abstractmethod
    def transcribe(
        self,
        request: TranscriptRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> TranscriptResult:
        """Transcribe one validated local media request.

        Args:
            request: Immutable media and transcription settings.
            progress_callback: Optional receiver of normalized progress events.

        Returns:
            A provider-independent completed transcript result.

        Raises:
            TranscriptError: If transcription cannot complete successfully.
        """
        ...

    @abstractmethod
    def backend_name(self) -> str:
        """Return the stable application identifier for this backend."""
        ...

    @abstractmethod
    def supported_formats(self) -> frozenset[str]:
        """Return lowercase media filename suffixes supported by this backend."""
        ...

    @abstractmethod
    def supported_tasks(self) -> frozenset[TranscriptTask]:
        """Return the transcript tasks supported by this backend."""
        ...
