"""
video_assembler.py — SignalForge Social Creative Engine v5

Assembles short-form vertical video (9:16 mp4) from a generated image
and snippet audio track using FFmpeg.

Safety guarantees
-----------------
- simulation_only: True on every result
- outbound_actions_taken: 0 on every result
- No publishing, scheduling, or platform API calls
- FFMPEG_ENABLED=false (default) → returns mock result without
  spawning any subprocess or writing any files

Environment variables
---------------------
FFMPEG_ENABLED    "1"/"true"/"yes"/"on" → invoke real FFmpeg binary
FFMPEG_OUTPUT_DIR  directory for output files (default: /tmp/signalforge_renders)
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_enabled(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _output_dir() -> str:
    path = os.getenv("FFMPEG_OUTPUT_DIR", "/tmp/signalforge_renders")
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VideoAssemblyResult:
    file_path: str = ""
    duration_seconds: float = 0.0
    resolution: str = ""
    has_captions: bool = False
    generation_engine: str = ""
    ffmpeg_enabled: bool = False
    mock: bool = True
    skip_reason: str = ""
    error: str = ""
    simulation_only: bool = True
    outbound_actions_taken: int = 0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "duration_seconds": self.duration_seconds,
            "resolution": self.resolution,
            "has_captions": self.has_captions,
            "generation_engine": self.generation_engine,
            "ffmpeg_enabled": self.ffmpeg_enabled,
            "mock": self.mock,
            "skip_reason": self.skip_reason,
            "error": self.error,
            "simulation_only": self.simulation_only,
            "outbound_actions_taken": self.outbound_actions_taken,
        }


# ---------------------------------------------------------------------------
# Core assembly function
# ---------------------------------------------------------------------------

def assemble_video(
    *,
    image_path: str = "",
    audio_path: str = "",
    output_dir: str = "",
    duration_seconds: float = 30.0,
    add_captions: bool = False,
    caption_text: str = "",
    resolution: str = "1080x1920",
    fade_duration: float = 0.5,
    generation_engine: str = "comfyui",
    asset_render_id: str = "",
) -> VideoAssemblyResult:
    """
    Assemble a vertical short-form video from image + audio.

    Returns a VideoAssemblyResult.  When FFMPEG_ENABLED is false (default),
    returns a mock result immediately without writing files or spawning
    any subprocesses.
    """
    ffmpeg_enabled = _env_enabled(os.getenv("FFMPEG_ENABLED", "false"))

    if not ffmpeg_enabled:
        render_id = asset_render_id or str(uuid.uuid4())
        mock_path = f"/tmp/signalforge_renders/mock_{render_id}.mp4"
        return VideoAssemblyResult(
            file_path=mock_path,
            duration_seconds=duration_seconds,
            resolution=resolution,
            has_captions=add_captions,
            generation_engine=generation_engine,
            ffmpeg_enabled=False,
            mock=True,
            skip_reason="ffmpeg_disabled",
            simulation_only=True,
            outbound_actions_taken=0,
        )

    # -----------------------------------------------------------------------
    # Real FFmpeg path — only reached when FFMPEG_ENABLED=true
    # -----------------------------------------------------------------------
    out_dir = output_dir or _output_dir()
    render_id = asset_render_id or str(uuid.uuid4())
    output_path = os.path.join(out_dir, f"{render_id}.mp4")

    width, height = _parse_resolution(resolution)

    # Build filter chain
    scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"

    if add_captions and caption_text:
        safe_text = caption_text.replace("'", "\\'").replace(":", "\\:")
        drawtext = (
            f"drawtext=text='{safe_text}':fontsize=36:fontcolor=white:x=(w-text_w)/2"
            f":y=h-100:box=1:boxcolor=black@0.5:boxborderw=8"
        )
        vf_chain = f"{scale_filter},{drawtext}"
    else:
        vf_chain = scale_filter

    # Fade filters (if fade_duration > 0)
    if fade_duration > 0:
        fade_in = f"fade=t=in:st=0:d={fade_duration}"
        fade_out = f"fade=t=out:st={max(0.0, duration_seconds - fade_duration)}:d={fade_duration}"
        vf_chain = f"{vf_chain},{fade_in},{fade_out}"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", image_path or _placeholder_image(render_id),
        "-i", audio_path,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-vf", vf_chain,
        "-t", str(duration_seconds),
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return VideoAssemblyResult(
                file_path="",
                duration_seconds=duration_seconds,
                resolution=resolution,
                has_captions=add_captions,
                generation_engine=generation_engine,
                ffmpeg_enabled=True,
                mock=False,
                error=f"FFmpeg failed (rc={result.returncode}): {result.stderr[:500]}",
                simulation_only=True,
                outbound_actions_taken=0,
            )
    except subprocess.TimeoutExpired:
        return VideoAssemblyResult(
            file_path="",
            duration_seconds=duration_seconds,
            resolution=resolution,
            has_captions=add_captions,
            generation_engine=generation_engine,
            ffmpeg_enabled=True,
            mock=False,
            error="FFmpeg process timed out after 300s.",
            simulation_only=True,
            outbound_actions_taken=0,
        )
    except FileNotFoundError:
        return VideoAssemblyResult(
            file_path="",
            duration_seconds=duration_seconds,
            resolution=resolution,
            has_captions=add_captions,
            generation_engine=generation_engine,
            ffmpeg_enabled=True,
            mock=False,
            error="FFmpeg binary not found. Install ffmpeg or set FFMPEG_ENABLED=false.",
            simulation_only=True,
            outbound_actions_taken=0,
        )

    return VideoAssemblyResult(
        file_path=output_path,
        duration_seconds=duration_seconds,
        resolution=resolution,
        has_captions=add_captions,
        generation_engine=generation_engine,
        ffmpeg_enabled=True,
        mock=False,
        simulation_only=True,
        outbound_actions_taken=0,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_resolution(resolution: str) -> tuple[int, int]:
    """Parse 'WxH' string into (width, height). Defaults to 1080x1920."""
    try:
        w_str, h_str = resolution.lower().split("x")
        return int(w_str), int(h_str)
    except (ValueError, AttributeError):
        return 1080, 1920


def _placeholder_image(render_id: str) -> str:
    """
    Return a path to a 1080x1920 placeholder PNG.
    Creates it in /tmp if the lavfi filter fails — used only when
    no image_path is provided and FFMPEG_ENABLED=true.
    """
    path = f"/tmp/signalforge_renders/placeholder_{render_id}.png"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=black:s=1080x1920:d=1",
                "-frames:v", "1",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass
    return path
