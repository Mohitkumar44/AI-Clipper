"""Application service orchestrating downloader, transcript, analyzer, and clipper services."""

from __future__ import annotations

import logging
from collections.abc import Callable
from time import monotonic

from src.analyzer.models import (
    AnalysisProgress,
    AnalyzerRequest,
    AnalyzerResult,
    ClipCandidate as AnalyzerClipCandidate,
)
from src.analyzer.service import AnalyzerService
from src.clipper.models import ClipCandidate, ClipProgress, ClipRequest, ClipResult
from src.clipper.service import ClipperService
from src.downloader.models import DownloadProgress, DownloadRequest, DownloadResult
from src.downloader.service import VideoDownloader
from src.transcript.models import TranscriptProgress, TranscriptRequest, TranscriptResult
from src.transcript.service import TranscriptService

from .exceptions import (
    AnalysisStageError,
    ClipRenderingStageError,
    DownloadStageError,
    PipelineError,
    TranscriptStageError,
)
from .models import PipelineProgress, PipelineRequest, PipelineResult, PipelineStage, ProgressCallback
from .validator import validate_pipeline_request, validate_pipeline_result


Clock = Callable[[], float]
TOTAL_STAGES = 4


class PipelineService:
    """Coordinate complete short-generation workflows through injected services."""

    def __init__(
        self,
        downloader_service: VideoDownloader,
        transcript_service: TranscriptService,
        analyzer_service: AnalyzerService,
        clipper_service: ClipperService,
        logger: logging.Logger,
        clock: Clock = monotonic,
    ) -> None:
        """Initialize orchestration with service-level dependencies only.

        Args:
            downloader_service: Existing service responsible for source download.
            transcript_service: Existing service responsible for transcription.
            analyzer_service: Existing service responsible for clip analysis.
            clipper_service: Existing service responsible for clip rendering.
            logger: Structured application logger supplied by the composition root.
            clock: Monotonic clock used for total workflow duration.
        """
        self._downloader_service = downloader_service
        self._transcript_service = transcript_service
        self._analyzer_service = analyzer_service
        self._clipper_service = clipper_service
        self._logger = logger
        self._clock = clock

    def run(
        self,
        request: PipelineRequest,
        progress_callback: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Run the full URL-to-rendered-clips workflow sequentially.

        Args:
            request: Immutable configuration for all workflow stages.
            progress_callback: Optional receiver of normalized pipeline progress.

        Returns:
            Immutable results from downloader, transcript, analyzer, and clipper stages.

        Raises:
            PipelineError: If any stage fails or returns an invalid result.
        """
        validate_pipeline_request(request)
        started_at = self._clock()
        self._logger.info("pipeline_started", extra={"event": "pipeline_started"})

        download_result = self._run_download_stage(request, progress_callback)
        transcript_result = self._run_transcript_stage(request, download_result, progress_callback)
        analyzer_result = self._run_analysis_stage(request, download_result, transcript_result, progress_callback)
        clip_result = self._run_render_stage(
            request,
            download_result,
            transcript_result,
            analyzer_result,
            progress_callback,
        )
        result = PipelineResult(
            download_result=download_result,
            transcript_result=transcript_result,
            analyzer_result=analyzer_result,
            clip_result=clip_result,
            processing_time_seconds=self._clock() - started_at,
        )
        validate_pipeline_result(result)
        self._emit_progress(progress_callback, PipelineStage.COMPLETED, TOTAL_STAGES)
        self._logger.info("pipeline_completed", extra={"event": "pipeline_completed"})
        return result

    def _run_download_stage(
        self,
        request: PipelineRequest,
        callback: ProgressCallback | None,
    ) -> DownloadResult:
        """Run downloader work and translate all failures to pipeline exceptions."""
        self._emit_progress(callback, PipelineStage.DOWNLOADING, 0)
        try:
            return self._downloader_service.download_video(
                DownloadRequest(request.source_url, request.download_config),
                self._download_progress_callback(callback),
            )
        except PipelineError:
            raise
        except Exception as error:
            raise DownloadStageError("The download stage failed.") from error

    def _run_transcript_stage(
        self,
        request: PipelineRequest,
        download_result: DownloadResult,
        callback: ProgressCallback | None,
    ) -> TranscriptResult:
        """Run transcript work and translate all failures to pipeline exceptions."""
        self._emit_progress(callback, PipelineStage.TRANSCRIBING, 1)
        try:
            return self._transcript_service.transcribe(
                TranscriptRequest(
                    media_path=download_result.local_path,
                    config=request.transcript_config,
                    backend_name=request.transcription_backend_name,
                ),
                self._transcript_progress_callback(callback),
            )
        except PipelineError:
            raise
        except Exception as error:
            raise TranscriptStageError("The transcript stage failed.") from error

    def _run_analysis_stage(
        self,
        request: PipelineRequest,
        download_result: DownloadResult,
        transcript_result: TranscriptResult,
        callback: ProgressCallback | None,
    ) -> AnalyzerResult:
        """Run analyzer work and translate all failures to pipeline exceptions."""
        self._emit_progress(callback, PipelineStage.ANALYZING, 2)
        try:
            return self._analyzer_service.analyze(
                AnalyzerRequest(
                    source_path=download_result.local_path,
                    transcript=transcript_result,
                    config=request.analysis_config,
                    analyzer_name=request.analyzer_name,
                ),
                self._analysis_progress_callback(callback),
            )
        except PipelineError:
            raise
        except Exception as error:
            raise AnalysisStageError("The analysis stage failed.") from error

    def _run_render_stage(
        self,
        request: PipelineRequest,
        download_result: DownloadResult,
        transcript_result: TranscriptResult,
        analyzer_result: AnalyzerResult,
        callback: ProgressCallback | None,
    ) -> ClipResult:
        """Run clip rendering and translate all failures to pipeline exceptions."""
        self._emit_progress(callback, PipelineStage.RENDERING, 3)
        candidates = tuple(_to_clip_candidate(candidate) for candidate in analyzer_result.candidates)
        try:
            return self._clipper_service.render_clips(
                ClipRequest(
                    download_result=download_result,
                    transcript_result=transcript_result,
                    analyzer_result=analyzer_result,
                    candidates=candidates,
                    configuration=request.clip_configuration,
                ),
                self._clip_progress_callback(callback),
            )
        except PipelineError:
            raise
        except Exception as error:
            raise ClipRenderingStageError("The clip-rendering stage failed.") from error

    def _download_progress_callback(
        self,
        callback: ProgressCallback | None,
    ) -> Callable[[DownloadProgress], None] | None:
        """Return a callback translating downloader progress into pipeline progress."""
        return lambda progress: self._emit_progress(callback, PipelineStage.DOWNLOADING, 0, progress.percentage)

    def _transcript_progress_callback(
        self,
        callback: ProgressCallback | None,
    ) -> Callable[[TranscriptProgress], None] | None:
        """Return a callback translating transcript progress into pipeline progress."""
        return lambda progress: self._emit_progress(callback, PipelineStage.TRANSCRIBING, 1, progress.progress_percentage)

    def _analysis_progress_callback(
        self,
        callback: ProgressCallback | None,
    ) -> Callable[[AnalysisProgress], None] | None:
        """Return a callback translating analyzer progress into pipeline progress."""
        return lambda progress: self._emit_progress(callback, PipelineStage.ANALYZING, 2, progress.progress_percentage)

    def _clip_progress_callback(
        self,
        callback: ProgressCallback | None,
    ) -> Callable[[ClipProgress], None] | None:
        """Return a callback translating clipper progress into pipeline progress."""
        return lambda progress: self._emit_progress(callback, PipelineStage.RENDERING, 3)

    def _emit_progress(
        self,
        callback: ProgressCallback | None,
        stage: PipelineStage,
        completed_stages: int,
        percentage: float | None = None,
    ) -> None:
        """Emit progress without allowing callback failures to stop the workflow."""
        if callback is None:
            return
        try:
            callback(PipelineProgress(stage, completed_stages, TOTAL_STAGES, percentage))
        except Exception:
            self._logger.exception("pipeline_progress_callback_failed", extra={"event": "progress_callback_failed"})


def _to_clip_candidate(candidate: AnalyzerClipCandidate) -> ClipCandidate:
    """Convert an analyzer candidate into the independent clipper candidate model."""
    return ClipCandidate(
        candidate_id=candidate.candidate_id,
        start_seconds=candidate.start_seconds,
        end_seconds=candidate.end_seconds,
        score=candidate.score,
        reason=candidate.reason,
        title_hint=candidate.hook,
    )
