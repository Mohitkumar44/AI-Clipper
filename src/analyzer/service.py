"""Application service coordinating provider-neutral transcript analysis."""

from __future__ import annotations

import logging

from src.core.config import ApplicationConfig

from .exceptions import AnalysisFailedError, AnalyzerError
from .models import AnalyzerRequest, AnalyzerResult
from .providers.base import AnalysisProvider, ProgressCallback
from .providers.factory import AnalysisProviderFactory
from .validator import validate_analyzer_request, validate_analyzer_result


class AnalyzerService:
    """Validate and delegate analyzer requests to an injected provider factory."""

    def __init__(
        self,
        application_config: ApplicationConfig,
        logger: logging.Logger,
        provider_factory: AnalysisProviderFactory,
    ) -> None:
        """Initialize the service with application-owned dependencies.

        Args:
            application_config: Shared immutable application configuration.
            logger: Structured application logger supplied by the composition root.
            provider_factory: Registry responsible for provider creation and defaults.
        """
        self._application_config = application_config
        self._logger = logger
        self._provider_factory = provider_factory

    def analyze(
        self,
        request: AnalyzerRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> AnalyzerResult:
        """Analyze one transcript using the selected provider.

        Args:
            request: Immutable source-media and transcript analysis request.
            progress_callback: Optional receiver of normalized analysis progress.

        Returns:
            A validated provider-independent analysis result.

        Raises:
            AnalyzerError: If validation, provider selection, or analysis fails.
        """
        validate_analyzer_request(request)
        provider = self._get_provider(request)
        self._logger.info(
            "analyzer_service_started",
            extra={"event": "analyzer_service_started", "provider": provider.provider_name()},
        )

        try:
            result = provider.analyze(request, progress_callback)
            validate_analyzer_result(result, request.config)
        except AnalyzerError:
            raise
        except Exception:
            self._logger.exception(
                "analyzer_service_failed",
                extra={"event": "analyzer_service_failed", "provider": provider.provider_name()},
            )
            raise AnalysisFailedError("The analysis provider failed unexpectedly.") from None

        self._logger.info(
            "analyzer_service_completed",
            extra={
                "event": "analyzer_service_completed",
                "provider": result.analyzer_name,
                "candidate_count": len(result.candidates),
            },
        )
        return result

    def _get_provider(self, request: AnalyzerRequest) -> AnalysisProvider:
        """Return the explicitly requested or configured default provider.

        Args:
            request: Validated analysis request that may name a provider.

        Returns:
            Provider instance selected by the injected factory.
        """
        if request.analyzer_name is None:
            return self._provider_factory.get_default_provider()
        return self._provider_factory.get_provider(request.analyzer_name)
