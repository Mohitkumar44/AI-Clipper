"""Application service coordinating provider-independent clip rendering."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic

from src.core.config import ApplicationConfig

from .backends.base import ClipRenderingBackend
from .backends.factory import ClipRenderingBackendFactory
from .exceptions import ClipRenderingError, ClipperError, InvalidClipRequestError
from .models import ClipProgress, ClipRequest, ClipResult, ClipStatus, ProgressCallback, RenderedClip
from .validator import validate_clip_request, validate_rendered_clip


Clock = Callable[[], float]


class ClipperService:
    """Validate and delegate clip rendering to an injected backend factory."""

    def __init__(
        self,
        application_config: ApplicationConfig,
        logger: logging.Logger,
        backend_factory: ClipRenderingBackendFactory,
        clock: Clock = monotonic,
    ) -> None:
        """Initialize the service with application-owned dependencies.

        Args:
            application_config: Shared configuration defining the controlled output root.
            logger: Structured application logger supplied by the composition root.
            backend_factory: Registry responsible for rendering backend creation.
            clock: Monotonic clock used to measure total rendering duration.
        """
        self._application_config = application_config
        self._logger = logger
        self._backend_factory = backend_factory
        self._clock = clock

    def render_clips(
        self,
        request: ClipRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> ClipResult:
        """Render every selected candidate in a validated clip request.

        Args:
            request: Immutable source media, candidate ranges, and output settings.
            progress_callback: Optional receiver of aggregated render progress.

        Returns:
            Immutable metadata for all successfully rendered clips.

        Raises:
            ClipperError: If validation, backend selection, or rendering fails.
        """
        validate_clip_request(request, self._application_config)
        backend = self._get_backend()
        total_clips = len(request.candidates)
        self._emit_progress(
            progress_callback,
            ClipProgress(status=ClipStatus.PREPARING, completed_clips=0, total_clips=total_clips),
        )
        self._logger.info(
            "clipper_service_started",
            extra={"event": "clipper_service_started", "backend": backend.backend_name()},
        )

        started_at = self._clock()
        rendered_clips: list[RenderedClip] = []
        try:
            backend.validate_backend(request.configuration)
            for index, candidate in enumerate(request.candidates):
                rendered_clip = backend.render_clip(
                    request,
                    candidate,
                    self._create_progress_callback(progress_callback, index, total_clips),
                )
                validate_rendered_clip(
                    rendered_clip,
                    request.configuration,
                    self._application_config,
                )
                if rendered_clip.candidate_id != candidate.candidate_id:
                    raise InvalidClipRequestError(
                        "The rendering backend returned a clip for a different candidate."
                    )
                rendered_clips.append(rendered_clip)
        except ClipperError:
            raise
        except Exception:
            self._logger.exception(
                "clipper_service_failed",
                extra={"event": "clipper_service_failed", "backend": backend.backend_name()},
            )
            raise ClipRenderingError("The rendering backend failed unexpectedly.") from None

        result = ClipResult(
            source_path=request.download_result.local_path,
            rendered_clips=tuple(rendered_clips),
            processing_time_seconds=self._clock() - started_at,
        )
        self._emit_progress(
            progress_callback,
            ClipProgress(status=ClipStatus.COMPLETED, completed_clips=total_clips, total_clips=total_clips),
        )
        self._logger.info(
            "clipper_service_completed",
            extra={
                "event": "clipper_service_completed",
                "backend": backend.backend_name(),
                "rendered_clip_count": len(result.rendered_clips),
            },
        )
        return result

    def _get_backend(self) -> ClipRenderingBackend:
        """Return the configured default rendering backend instance."""
        return self._backend_factory.get_default_backend()

    def _create_progress_callback(
        self,
        callback: ProgressCallback | None,
        completed_clips: int,
        total_clips: int,
    ) -> ProgressCallback | None:
        """Create a callback that converts single-render progress into aggregate progress."""
        if callback is None:
            return None

        def report(progress: ClipProgress) -> None:
            """Forward backend status with service-level clip counts."""
            completed = completed_clips
            if progress.status is ClipStatus.COMPLETED:
                completed += 1
            self._emit_progress(
                callback,
                ClipProgress(
                    status=progress.status,
                    completed_clips=completed,
                    total_clips=total_clips,
                    candidate_id=progress.candidate_id,
                    message=progress.message,
                ),
            )

        return report

    def _emit_progress(self, callback: ProgressCallback | None, progress: ClipProgress) -> None:
        """Notify callers without allowing callback failures to halt rendering."""
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            self._logger.exception(
                "clipper_progress_callback_failed",
                extra={"event": "progress_callback_failed"},
            )
