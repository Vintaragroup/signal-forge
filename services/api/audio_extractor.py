"""
Audio extractor abstraction — Social Creative Engine v3/v4.

When ``FFMPEG_ENABLED=false`` (default), all extraction jobs are recorded
with ``status='skipped'`` and ``skip_reason='ffmpeg_disabled'``.  No files
are downloaded, read, or written.  No URLs are accessed.

When ``FFMPEG_ENABLED=true``, ``FFmpegAudioExtractor`` is used.  It runs
``ffmpeg`` as a subprocess on a local file path only.  Remote URLs are never
fetched.  The caller must supply a resolved local ``media_path`` from a
registered ``MediaIntakeRecord`` with ``intake_method='local_file'``.

Safety guarantee
----------------
* No audio is ever fetched from a remote URL.
* Source content must be ``approved=True`` before extraction is attempted;
  the enforcement gate lives in the API endpoint, not in this module.
* simulation_only = True on all records produced by this module.
* outbound_actions_taken = 0 always.

Adding a cloud extractor in the future
---------------------------------------
Implement a class with an ``extract()`` method matching
``StubAudioExtractor.extract``, returning an ``AudioExtractionResult``.
Register it in ``get_audio_extractor()`` under its env-var name.

Env vars
--------
``FFMPEG_ENABLED=false`` (default)
    Set ``FFMPEG_ENABLED=true`` to use the local FFmpeg extractor.
``FFMPEG_OUTPUT_DIR=/tmp/signalforge_audio`` (default)
    Directory where extracted audio files are written.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AudioExtractionResult:
    """Value object returned by any audio extractor implementation."""

    status: str  # "skipped" | "complete" | "failed"
    skip_reason: str = ""
    output_path: str = ""
    duration_seconds: float = 0.0
    error: str = ""
    extractor: str = "stub"
    simulation_only: bool = True
    outbound_actions_taken: int = 0


class StubAudioExtractor:
    """
    Stub extractor — used when ``FFMPEG_ENABLED=false`` (the default).

    Always returns ``status='skipped'``.  No files are touched.
    """

    extractor_name: str = "stub"

    def extract(
        self,
        source_url: str = "",
        media_path: str = "",
        output_dir: str = "/tmp",
    ) -> AudioExtractionResult:
        return AudioExtractionResult(
            status="skipped",
            skip_reason="ffmpeg_disabled",
            extractor=self.extractor_name,
            simulation_only=True,
            outbound_actions_taken=0,
        )


class FFmpegAudioExtractor:
    """
    Real audio extractor using a locally installed ``ffmpeg`` binary.

    Only processes approved local file paths.  Never fetches remote URLs.
    Writes extracted mono 16 kHz WAV to ``output_dir``.

    If ``ffmpeg`` is not installed or not on PATH, returns ``status='failed'``
    with an informative ``error`` message.
    """

    extractor_name: str = "ffmpeg"

    def extract(
        self,
        source_url: str = "",
        media_path: str = "",
        output_dir: str = "/tmp/signalforge_audio",
    ) -> AudioExtractionResult:
        # Never attempt to fetch a remote URL
        if not media_path or not media_path.strip():
            return AudioExtractionResult(
                status="failed",
                error="media_path is required for FFmpeg extraction. "
                      "Remote URL download is not enabled.",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )

        clean_path = media_path.strip()

        # Guard: file must exist
        if not os.path.isfile(clean_path):
            return AudioExtractionResult(
                status="failed",
                error=f"media file not found: {clean_path}",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )

        # Guard: ffmpeg must be on PATH
        if not shutil.which("ffmpeg"):
            return AudioExtractionResult(
                status="failed",
                error="ffmpeg not found on PATH. Install ffmpeg or set FFMPEG_ENABLED=false.",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )

        # Build output path
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as exc:
            return AudioExtractionResult(
                status="failed",
                error=f"cannot create output directory: {exc}",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )

        stem = Path(clean_path).stem
        output_path = os.path.join(output_dir, f"{stem}_extracted.wav")

        # Run ffmpeg: extract audio as mono 16 kHz WAV
        cmd = [
            "ffmpeg",
            "-y",               # overwrite without prompt
            "-i", clean_path,   # input: local file only
            "-vn",              # no video
            "-ar", "16000",     # 16 kHz sample rate
            "-ac", "1",         # mono
            "-f", "wav",
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            return AudioExtractionResult(
                status="failed",
                error="ffmpeg process timed out (300s).",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )
        except OSError as exc:
            return AudioExtractionResult(
                status="failed",
                error=f"ffmpeg execution error: {exc}",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )

        if result.returncode != 0:
            stderr_snippet = (result.stderr or "")[-400:]
            return AudioExtractionResult(
                status="failed",
                error=f"ffmpeg exited {result.returncode}: {stderr_snippet}",
                extractor=self.extractor_name,
                simulation_only=True,
                outbound_actions_taken=0,
            )

        # Attempt to read duration from ffmpeg stderr (best effort)
        duration = _parse_duration_from_ffmpeg_output(result.stderr or "")

        return AudioExtractionResult(
            status="complete",
            output_path=output_path,
            duration_seconds=duration,
            extractor=self.extractor_name,
            simulation_only=True,
            outbound_actions_taken=0,
        )


def _parse_duration_from_ffmpeg_output(stderr: str) -> float:
    """
    Parse duration (seconds) from ffmpeg stderr output.

    Looks for: ``Duration: HH:MM:SS.mmm``
    Returns 0.0 if not found or on parse error.
    """
    import re

    match = re.search(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    if not match:
        return 0.0
    try:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return round(h * 3600 + m * 60 + s, 3)
    except (ValueError, IndexError):
        return 0.0


def get_audio_extractor() -> StubAudioExtractor | FFmpegAudioExtractor:
    """Return the configured audio extractor instance.

    Returns ``FFmpegAudioExtractor`` when ``FFMPEG_ENABLED=true``,
    otherwise returns ``StubAudioExtractor``.
    """
    ffmpeg_enabled = os.getenv("FFMPEG_ENABLED", "false").lower() in (
        "1", "true", "yes", "on"
    )
    if ffmpeg_enabled:
        output_dir = os.getenv(
            "FFMPEG_OUTPUT_DIR", "/tmp/signalforge_audio"
        )
        extractor = FFmpegAudioExtractor()
        extractor._output_dir = output_dir  # type: ignore[attr-defined]
        return extractor
    return StubAudioExtractor()

