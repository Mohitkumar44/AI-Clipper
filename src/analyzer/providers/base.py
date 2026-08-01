"""Abstract contract for provider-independent transcript analysis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from ..models import AnalysisProgress, AnalyzerRequest, AnalyzerResult


ProgressCallback = Callable[[AnalysisProgress], None]


class AnalysisProvider(ABC):
    """Common interface implemented by all transcript-analysis providers."""

    @abstractmethod
    def analyze(
        self,
        request: AnalyzerRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> AnalyzerResult:
        """Analyze a validated transcript and return clip recommendations.

        Args:
            request: Immutable transcript-analysis request.
            progress_callback: Optional receiver for normalized progress events.

        Returns:
            Provider-independent analysis output.

        Raises:
            AnalyzerError: If the provider cannot complete the analysis.
        """
        ...

    @abstractmethod
    def provider_name(self) -> str:
        """Return the stable application identifier for this provider.

        Returns:
            A lowercase provider identifier suitable for application selection.
        """
        ...

    @abstractmethod
    def supported_models(self) -> tuple[str, ...]:
        """Return configured model identifiers supported by this provider.

        Returns:
            An immutable sequence of provider model identifiers.
        """
        ...

    @abstractmethod
    def supports_language(self, language_code: str) -> bool:
        """Return whether this provider supports a requested output language.

        Args:
            language_code: Normalized language identifier to evaluate.

        Returns:
            ``True`` when the language can be processed by this provider.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return whether the provider is currently ready to accept analysis work.

        Returns:
            ``True`` when the provider reports itself as operational.
        """
        ...
