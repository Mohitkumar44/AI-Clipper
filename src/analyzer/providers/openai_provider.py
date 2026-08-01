"""OpenAI-backed adapter for provider-independent transcript analysis."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from time import monotonic
from typing import Protocol

from ..exceptions import (
    AnalysisFailedError,
    AnalyzerConfigurationError,
    AnalyzerError,
    InvalidAnalysisResultError,
    ProviderCommunicationError,
    RateLimitExceededError,
)
from ..models import (
    AnalysisProgress,
    AnalysisStatus,
    AnalyzerRequest,
    AnalyzerResult,
    ClipCandidate,
    ViralMoment,
    ViralMomentType,
)
from ..validator import validate_analyzer_request, validate_analyzer_result
from .base import AnalysisProvider, ProgressCallback


class ResponsesClient(Protocol):
    """Minimal injected Responses API surface required by this provider."""

    def create(self, **kwargs: object) -> object:
        """Create one provider response from a structured analysis request."""


class OpenAIClient(Protocol):
    """Minimal injected client surface required by this provider."""

    responses: ResponsesClient


Clock = Callable[[], float]


class OpenAIAnalysisProvider(AnalysisProvider):
    """Adapt an injected OpenAI-compatible client to the analysis-provider contract."""

    def __init__(
        self,
        client: OpenAIClient,
        logger: logging.Logger,
        model_name: str,
        timeout_seconds: float,
        clock: Clock = monotonic,
    ) -> None:
        """Initialize the provider with application-owned dependencies.

        Args:
            client: Authenticated API client created by the composition root.
            logger: Structured application logger.
            model_name: Provider model identifier used for analysis.
            timeout_seconds: Maximum duration for one provider request.
            clock: Monotonic clock used to measure analysis duration.

        Raises:
            AnalyzerConfigurationError: If model or timeout configuration is invalid.
        """
        if not isinstance(model_name, str) or not model_name.strip():
            raise AnalyzerConfigurationError("model_name must not be blank.")
        if not isinstance(timeout_seconds, int | float) or isinstance(timeout_seconds, bool):
            raise AnalyzerConfigurationError("timeout_seconds must be numeric.")
        if timeout_seconds <= 0:
            raise AnalyzerConfigurationError("timeout_seconds must be positive.")
        self._client = client
        self._logger = logger
        self._model_name = model_name
        self._timeout_seconds = float(timeout_seconds)
        self._clock = clock

    def analyze(
        self,
        request: AnalyzerRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> AnalyzerResult:
        """Analyze a transcript using the injected API client.

        Args:
            request: Validated source media, transcript, and analysis settings.
            progress_callback: Optional receiver of normalized progress events.

        Returns:
            Provider-independent candidate clips and viral moments.

        Raises:
            AnalyzerError: If validation, provider communication, or response
                parsing cannot complete successfully.
        """
        validate_analyzer_request(request)
        self._emit_progress(progress_callback, AnalysisProgress(status=AnalysisStatus.PREPARING))
        self._emit_progress(progress_callback, AnalysisProgress(status=AnalysisStatus.ANALYZING))
        self._logger.info(
            "openai_analysis_started",
            extra={"event": "analysis_started", "provider": self.provider_name()},
        )

        started_at = self._clock()
        try:
            response = self._client.responses.create(
                model=self._model_name,
                input=self._build_provider_input(request),
                text={"format": _response_format()},
                timeout=self._timeout_seconds,
            )
            result = self._parse_response(response, request, self._clock() - started_at)
            validate_analyzer_result(result, request.config)
        except AnalyzerError:
            raise
        except Exception as error:
            self._logger.exception(
                "openai_analysis_failed",
                extra={"event": "analysis_failed", "provider": self.provider_name()},
            )
            raise _translate_provider_error(error) from None

        self._emit_progress(progress_callback, AnalysisProgress(status=AnalysisStatus.COMPLETED))
        self._logger.info(
            "openai_analysis_completed",
            extra={
                "event": "analysis_completed",
                "provider": self.provider_name(),
                "candidate_count": len(result.candidates),
            },
        )
        return result

    def provider_name(self) -> str:
        """Return the stable application identifier for this adapter."""
        return "openai"

    def supported_models(self) -> tuple[str, ...]:
        """Return the model configured for this provider instance."""
        return (self._model_name,)

    def supports_language(self, language_code: str) -> bool:
        """Return whether a normalized language code is accepted for analysis output."""
        return isinstance(language_code, str) and bool(language_code.strip())

    def health_check(self) -> bool:
        """Return whether the injected client exposes the required Responses surface."""
        return callable(getattr(getattr(self._client, "responses", None), "create", None))

    def _build_provider_input(self, request: AnalyzerRequest) -> list[dict[str, str]]:
        """Build a provider request from public transcript-analysis models."""
        transcript_payload = {
            "language": request.transcript.language.code,
            "full_text": request.transcript.full_text,
            "segments": [
                {
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "text": segment.text,
                }
                for segment in request.transcript.segments
            ],
            "constraints": {
                "maximum_candidates": request.config.maximum_candidates,
                "minimum_clip_duration_seconds": request.config.minimum_clip_duration_seconds,
                "maximum_clip_duration_seconds": request.config.maximum_clip_duration_seconds,
                "target_language_code": request.config.target_language_code,
                "custom_instructions": request.config.custom_instructions,
                "include_transcript_excerpt": request.config.include_transcript_excerpt,
            },
        }
        return [
            {
                "role": "system",
                "content": (
                    "Identify high-retention short-form video moments. Return only data that "
                    "matches the requested JSON schema and use transcript timestamps exactly."
                ),
            },
            {"role": "user", "content": json.dumps(transcript_payload, ensure_ascii=False)},
        ]

    def _parse_response(
        self,
        response: object,
        request: AnalyzerRequest,
        processing_time_seconds: float,
    ) -> AnalyzerResult:
        """Convert structured provider output into the public result contract."""
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str) or not output_text.strip():
            raise InvalidAnalysisResultError("The provider returned no structured analysis output.")
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError as error:
            raise InvalidAnalysisResultError("The provider returned invalid JSON output.") from error
        if not isinstance(payload, Mapping):
            raise InvalidAnalysisResultError("The provider response must be a JSON object.")

        candidates = tuple(_parse_candidate(item) for item in _required_list(payload, "candidates"))
        viral_moments = tuple(
            _parse_viral_moment(item) for item in _required_list(payload, "viral_moments")
        )
        return AnalyzerResult(
            source_path=request.source_path,
            candidates=candidates,
            viral_moments=viral_moments,
            analyzer_name=self.provider_name(),
            processing_time_seconds=processing_time_seconds,
        )

    def _emit_progress(self, callback: ProgressCallback | None, progress: AnalysisProgress) -> None:
        """Notify a caller without allowing callback failures to halt analysis."""
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            self._logger.exception(
                "openai_analysis_progress_callback_failed",
                extra={"event": "progress_callback_failed", "provider": self.provider_name()},
            )


def _response_format() -> dict[str, object]:
    """Return the JSON-schema response format expected from the provider."""
    return {
        "type": "json_schema",
        "name": "clip_analysis",
        "strict": False,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["candidates", "viral_moments"],
            "properties": {
                "candidates": {"type": "array", "items": {"type": "object"}},
                "viral_moments": {"type": "array", "items": {"type": "object"}},
            },
        },
    }


def _required_list(payload: Mapping[str, object], field_name: str) -> Sequence[object]:
    """Return a required response list or raise an application result exception."""
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise InvalidAnalysisResultError(f"The provider response is missing {field_name}.")
    return value


def _parse_candidate(value: object) -> ClipCandidate:
    """Convert one provider candidate object into a public clip candidate."""
    item = _required_mapping(value, "candidate")
    return ClipCandidate(
        candidate_id=_required_string(item, "candidate_id"),
        start_seconds=_required_number(item, "start_seconds"),
        end_seconds=_required_number(item, "end_seconds"),
        score=_required_number(item, "score"),
        reason=_required_string(item, "reason"),
        hook=_optional_string(item.get("hook")),
        transcript_excerpt=_optional_string(item.get("transcript_excerpt")),
    )


def _parse_viral_moment(value: object) -> ViralMoment:
    """Convert one provider moment object into a public viral-moment model."""
    item = _required_mapping(value, "viral moment")
    try:
        moment_type = ViralMomentType(_required_string(item, "moment_type"))
    except ValueError as error:
        raise InvalidAnalysisResultError("The provider returned an unsupported moment type.") from error
    return ViralMoment(
        moment_id=_required_string(item, "moment_id"),
        moment_type=moment_type,
        start_seconds=_required_number(item, "start_seconds"),
        end_seconds=_required_number(item, "end_seconds"),
        score=_required_number(item, "score"),
        explanation=_required_string(item, "explanation"),
    )


def _required_mapping(value: object, label: str) -> Mapping[str, object]:
    """Return a required JSON object or raise an application result exception."""
    if not isinstance(value, Mapping):
        raise InvalidAnalysisResultError(f"The provider returned an invalid {label}.")
    return value


def _required_string(payload: Mapping[str, object], field_name: str) -> str:
    """Return a required non-blank JSON string."""
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidAnalysisResultError(f"The provider returned an invalid {field_name}.")
    return value


def _optional_string(value: object) -> str | None:
    """Return an optional string value or raise on incompatible JSON types."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidAnalysisResultError("The provider returned an invalid optional text value.")
    return value


def _required_number(payload: Mapping[str, object], field_name: str) -> float:
    """Return a required non-boolean JSON number."""
    value = payload.get(field_name)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise InvalidAnalysisResultError(f"The provider returned an invalid {field_name}.")
    return float(value)


def _translate_provider_error(error: Exception) -> AnalyzerError:
    """Map injected-client failures to stable analyzer-domain exceptions."""
    status_code = getattr(error, "status_code", None)
    message = str(error).lower()
    if status_code == 429 or "rate limit" in message:
        return RateLimitExceededError("The analysis provider rate limit was exceeded.")
    if any(keyword in message for keyword in ("timeout", "connection", "network", "unavailable")):
        return ProviderCommunicationError("The analysis provider could not be reached.")
    return AnalysisFailedError("The analysis provider could not complete the request.")
