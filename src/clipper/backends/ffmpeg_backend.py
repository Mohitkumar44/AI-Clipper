"""FFmpeg implementation of the provider-independent clip-rendering contract."""

from __future__ import annotations

import hashlib
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from ..exceptions import (
    ClipRenderingError,
    FFmpegNotFoundError,
    InvalidClipRequestError,
    OutputWriteError,
    UnsupportedFormatError,
)
from ..models import (
    ClipCandidate,
    ClipConfiguration,
    ClipFormat,
    ClipProgress,
    ClipRequest,
    ClipStatus,
    ProgressCallback,
    RenderedClip,
)
from ..validator import validate_clip_candidate, validate_timestamp_range
from .base import ClipRenderingBackend


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class FFmpegClipRenderingBackend(ClipRenderingBackend):
    """Render one source-media range through a safely invoked FFmpeg executable."""

    def __init__(
        self,
        ffmpeg_executable: Path,
        logger: logging.Logger,
        timeout_seconds: float,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        """Initialize the backend with injected process dependencies.

        Args:
            ffmpeg_executable: Absolute or configured path to the FFmpeg executable.
            logger: Structured application logger supplied by the composition root.
            timeout_seconds: Maximum duration for each FFmpeg process invocation.
            command_runner: Injectable subprocess runner used for deterministic tests.

        Raises:
            InvalidClipRequestError: If executable or timeout configuration is invalid.
        """
        if not isinstance(ffmpeg_executable, Path):
            raise InvalidClipRequestError("ffmpeg_executable must be a pathlib.Path instance.")
        if not isinstance(timeout_seconds, int | float) or isinstance(timeout_seconds, bool):
            raise InvalidClipRequestError("timeout_seconds must be numeric.")
        if timeout_seconds <= 0:
            raise InvalidClipRequestError("timeout_seconds must be positive.")
        if not callable(command_runner):
            raise InvalidClipRequestError("command_runner must be callable.")
        self._ffmpeg_executable = ffmpeg_executable
        self._logger = logger
        self._timeout_seconds = float(timeout_seconds)
        self._command_runner = command_runner

    def render_clip(
        self,
        request: ClipRequest,
        candidate: ClipCandidate,
        progress_callback: ProgressCallback | None = None,
    ) -> RenderedClip:
        """Render one validated candidate range using FFmpeg argument-list execution.

        Args:
            request: Immutable request containing source and output context.
            candidate: Timestamp range selected for one rendered output.
            progress_callback: Optional receiver of normalized rendering progress.

        Returns:
            Metadata for the successfully rendered local clip.

        Raises:
            ClipperError: If FFmpeg is unavailable, fails, or produces no output.
        """
        if not isinstance(request, ClipRequest):
            raise InvalidClipRequestError("request must be a ClipRequest instance.")
        validate_clip_candidate(candidate)
        self.validate_backend(request.configuration)

        output_path = self._build_output_path(request.configuration, candidate)
        self._validate_output_path(output_path, request.configuration)
        arguments = self._build_ffmpeg_arguments(request, candidate, output_path)
        self._emit_progress(
            progress_callback,
            ClipProgress(status=ClipStatus.CUTTING, completed_clips=0, total_clips=1, candidate_id=candidate.candidate_id),
        )
        self._logger.info(
            "ffmpeg_clip_render_started",
            extra={"event": "clip_render_started", "backend": self.backend_name()},
        )

        try:
            completed_process = self._command_runner(
                arguments,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                shell=False,
            )
        except FileNotFoundError as error:
            raise FFmpegNotFoundError("The configured FFmpeg executable was not found.") from error
        except subprocess.TimeoutExpired as error:
            raise ClipRenderingError("FFmpeg exceeded the configured render timeout.") from error
        except PermissionError as error:
            raise OutputWriteError("FFmpeg could not write the requested output clip.") from error
        except OSError as error:
            raise ClipRenderingError("FFmpeg could not start the requested render operation.") from error

        if completed_process.returncode != 0:
            self._logger.error(
                "ffmpeg_clip_render_failed",
                extra={"event": "clip_render_failed", "backend": self.backend_name()},
            )
            raise ClipRenderingError("FFmpeg could not render the requested clip.")
        if not output_path.is_file():
            raise OutputWriteError("FFmpeg completed without producing the requested output clip.")

        duration_seconds = candidate.end_seconds - candidate.start_seconds
        rendered_clip = RenderedClip(
            candidate_id=candidate.candidate_id,
            output_path=output_path,
            start_seconds=candidate.start_seconds,
            end_seconds=candidate.end_seconds,
            output_format=request.configuration.output_format,
            duration_seconds=duration_seconds,
        )
        self._emit_progress(
            progress_callback,
            ClipProgress(status=ClipStatus.COMPLETED, completed_clips=1, total_clips=1, candidate_id=candidate.candidate_id),
        )
        self._logger.info(
            "ffmpeg_clip_render_completed",
            extra={"event": "clip_render_completed", "backend": self.backend_name()},
        )
        return rendered_clip

    def validate_backend(self, configuration: ClipConfiguration) -> None:
        """Verify FFmpeg availability and selected container-format support.

        Args:
            configuration: Output settings required by the render operation.

        Raises:
            FFmpegNotFoundError: If the executable cannot be run.
            UnsupportedFormatError: If the selected format is unsupported.
            ClipRenderingError: If FFmpeg fails its availability probe.
        """
        if not isinstance(configuration, ClipConfiguration):
            raise InvalidClipRequestError("configuration must be a ClipConfiguration instance.")
        if configuration.output_format not in self.supported_formats():
            raise UnsupportedFormatError("The requested output format is unsupported by FFmpeg.")
        try:
            completed_process = self._command_runner(
                [str(self._ffmpeg_executable), "-version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                shell=False,
            )
        except FileNotFoundError as error:
            raise FFmpegNotFoundError("The configured FFmpeg executable was not found.") from error
        except subprocess.TimeoutExpired as error:
            raise ClipRenderingError("FFmpeg did not respond to its availability check.") from error
        except OSError as error:
            raise ClipRenderingError("FFmpeg could not be started for validation.") from error
        if completed_process.returncode != 0:
            raise ClipRenderingError("FFmpeg failed its availability check.")

    def backend_name(self) -> str:
        """Return the stable application identifier for this rendering backend."""
        return "ffmpeg"

    def supported_formats(self) -> frozenset[ClipFormat]:
        """Return container formats supported by this FFmpeg implementation."""
        return frozenset({ClipFormat.MP4, ClipFormat.WEBM, ClipFormat.MOV})

    def _build_ffmpeg_arguments(
        self,
        request: ClipRequest,
        candidate: ClipCandidate,
        output_path: Path,
    ) -> list[str]:
        """Build a complete FFmpeg argument list without constructing shell commands."""
        validate_timestamp_range(candidate.start_seconds, candidate.end_seconds)
        duration_seconds = candidate.end_seconds - candidate.start_seconds
        arguments = [
            str(self._ffmpeg_executable),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-ss",
            _format_seconds(candidate.start_seconds),
            "-i",
            str(request.download_result.local_path),
            "-t",
            _format_seconds(duration_seconds),
            "-c:v",
            request.configuration.video_codec,
        ]
        if request.configuration.include_audio:
            arguments.extend(["-c:a", request.configuration.audio_codec])
        else:
            arguments.append("-an")
        arguments.extend(["-y" if request.configuration.overwrite else "-n", str(output_path)])
        return arguments

    def _build_output_path(self, configuration: ClipConfiguration, candidate: ClipCandidate) -> Path:
        """Generate a filesystem-safe filename without trusting candidate text."""
        identifier_hash = hashlib.sha256(candidate.candidate_id.encode("utf-8")).hexdigest()[:16]
        return configuration.output_directory / f"clip_{identifier_hash}.{configuration.output_format.value}"

    def _validate_output_path(self, output_path: Path, configuration: ClipConfiguration) -> None:
        """Ensure a generated output path remains inside its configured directory."""
        try:
            output_path.resolve().relative_to(configuration.output_directory.resolve())
        except (OSError, ValueError) as error:
            raise OutputWriteError("Generated output path escapes output_directory.") from error
        if output_path.suffix != f".{configuration.output_format.value}":
            raise OutputWriteError("Generated output path is invalid.")

    def _emit_progress(self, callback: ProgressCallback | None, progress: ClipProgress) -> None:
        """Notify callers without allowing callback failures to halt rendering."""
        if callback is None:
            return
        try:
            callback(progress)
        except Exception:
            self._logger.exception(
                "ffmpeg_clip_progress_callback_failed",
                extra={"event": "progress_callback_failed", "backend": self.backend_name()},
            )


def _format_seconds(value: float) -> str:
    """Format a validated timestamp as a locale-independent FFmpeg argument."""
    return f"{value:.6f}"
