"""
video_assembler.py — SignalForge Social Creative Engine v5.5

Assembles short-form vertical video (9:16 mp4) from a generated image
and snippet audio track using FFmpeg.

Safety guarantees
-----------------
- simulation_only: True on every result
- outbound_actions_taken: 0 on every result
- No publishing, scheduling, or platform API calls
- FFMPEG_ENABLED=false (default) → returns mock result without
  spawning any subprocess or writing any files

New in v5.5
-----------
- assembly_status: "success" | "failed" | "skipped" | "mock"
- assembly_engine: "ffmpeg" | "mock"
- generate_test_tone(): creates a safe local sine-wave WAV for demo/test
  renders when no source_audio_path is provided
- ffmpeg_diagnostics(): returns dict with ffmpeg_available, path, version

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
    assembly_status: str = "mock"   # "success" | "failed" | "skipped" | "mock"
    assembly_engine: str = "mock"   # "ffmpeg" | "mock"
    image_source: str = ""          # "comfyui" | "placeholder" | ""
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
            "assembly_status": self.assembly_status,
            "assembly_engine": self.assembly_engine,
            "image_source": self.image_source,
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
    preserve_original_audio: bool = True,
) -> VideoAssemblyResult:
    """
    Assemble a vertical short-form video from image + audio.

    Returns a VideoAssemblyResult.  When FFMPEG_ENABLED is false (default),
    returns a mock result immediately without writing files or spawning
    any subprocesses.

    Audio behaviour
    ---------------
    * ``audio_path`` non-empty  → source audio is used unchanged (original
      audio preserved; no cloning, no rewriting).
    * ``audio_path`` empty AND ``FFMPEG_ENABLED=true``  → ``generate_test_tone()``
      creates a safe local sine-wave WAV as a demo/test fallback only.
    * ``preserve_original_audio=True`` (default) — informational flag confirming
      the operator's intent; the function already preserves audio by default.
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
            assembly_status="mock",
            assembly_engine="mock",
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

    # If no audio provided, generate a local test tone (safe, no external download)
    effective_audio = audio_path
    if not effective_audio:
        effective_audio = generate_test_tone(
            duration_seconds=duration_seconds,
            output_path=os.path.join(out_dir, f"testtone_{render_id}.wav"),
        )

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

    # Use image_path only if the file actually exists; otherwise generate a placeholder.
    effective_image = (
        image_path if (image_path and os.path.isfile(image_path)) else _placeholder_image(render_id)
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", effective_image,
        "-i", effective_audio,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "28",
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
                assembly_status="failed",
                assembly_engine="ffmpeg",
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
            assembly_status="failed",
            assembly_engine="ffmpeg",
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
            assembly_status="failed",
            assembly_engine="ffmpeg",
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
        assembly_status="success",
        assembly_engine="ffmpeg",
        simulation_only=True,
        outbound_actions_taken=0,
    )


# ---------------------------------------------------------------------------
# Multi-image sequence assembly (Ken Burns effect)
# ---------------------------------------------------------------------------

def assemble_video_sequence(
    *,
    image_paths: list[str],
    audio_path: str = "",
    output_dir: str = "",
    duration_seconds: float = 30.0,
    add_captions: bool = False,
    caption_text: str = "",
    resolution: str = "1080x1920",
    generation_engine: str = "comfyui",
    asset_render_id: str = "",
    preserve_original_audio: bool = True,
) -> "VideoAssemblyResult":
    """
    Assemble a vertical short-form video from multiple images (one per scene
    beat) with a Ken Burns (zoompan) effect applied to each, then concatenated.

    Falls back to ``assemble_video`` with the first image when FFMPEG_ENABLED
    is false (returns mock) or when ``image_paths`` has only one entry.

    Safety: simulation_only=True, outbound_actions_taken=0 on every result.
    Audio: ``audio_path`` is preserved unmodified (never re-encoded by default).
    """
    ffmpeg_enabled = _env_enabled(os.getenv("FFMPEG_ENABLED", "false"))

    # Normalise: filter only existing files
    valid_paths = [p for p in (image_paths or []) if p and os.path.isfile(p)]

    # Mock path or single-image fallback
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
            assembly_status="mock",
            assembly_engine="mock",
            skip_reason="ffmpeg_disabled",
            simulation_only=True,
            outbound_actions_taken=0,
        )

    if len(valid_paths) <= 1:
        single = valid_paths[0] if valid_paths else ""
        return assemble_video(
            image_path=single,
            audio_path=audio_path,
            output_dir=output_dir,
            duration_seconds=duration_seconds,
            add_captions=add_captions,
            caption_text=caption_text,
            resolution=resolution,
            generation_engine=generation_engine,
            asset_render_id=asset_render_id,
            preserve_original_audio=preserve_original_audio,
        )

    out_dir = output_dir or _output_dir()
    render_id = asset_render_id or str(uuid.uuid4())
    output_path = os.path.join(out_dir, f"{render_id}.mp4")
    width, height = _parse_resolution(resolution)

    # Per-frame duration (evenly distributed)
    num_frames = len(valid_paths)
    frame_dur = duration_seconds / num_frames
    # Ken Burns: frames per segment at 25 fps
    fps = 25
    frame_count = max(1, int(round(frame_dur * fps)))

    # Audio
    effective_audio = audio_path
    if not effective_audio:
        effective_audio = generate_test_tone(
            duration_seconds=duration_seconds,
            output_path=os.path.join(out_dir, f"testtone_{render_id}.wav"),
        )

    # Caption drawtext filter suffix (applied after concat)
    drawtext_filter = ""
    if add_captions and caption_text:
        safe_text = caption_text.replace("'", "\\'").replace(":", "\\:")
        drawtext_filter = (
            f",drawtext=text='{safe_text}':fontsize=36:fontcolor=white"
            f":x=(w-text_w)/2:y=h-100:box=1:boxcolor=black@0.5:boxborderw=8"
        )

    # Build FFmpeg filter_complex with one zoompan segment per image
    # Each image is scaled/padded then Ken Burns'd for frame_count frames.
    scale_pad = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )

    filter_parts: list[str] = []
    input_args: list[str] = []
    for i, img_path in enumerate(valid_paths):
        input_args += ["-loop", "1", "-t", str(frame_dur + 0.1), "-i", img_path]
        # Alternate between zoom-in and zoom-out Ken Burns passes
        if i % 2 == 0:
            zoom_expr = f"'min(zoom+0.0015,1.5)'"
            x_expr = f"'iw/2-(iw/zoom/2)'"
            y_expr = f"'ih/2-(ih/zoom/2)'"
        else:
            zoom_expr = f"'if(lte(zoom,1.0),1.5,max(1.001,zoom-0.0015))'"
            x_expr = f"'iw/2-(iw/zoom/2)+{i % 3}*(iw/zoom/8)'"
            y_expr = f"'ih/2-(ih/zoom/2)'"
        zoompan = (
            f"zoompan=z={zoom_expr}:x={x_expr}:y={y_expr}"
            f":d={frame_count}:s={width}x{height}:fps={fps}"
        )
        filter_parts.append(
            f"[{i}:v]{scale_pad},{zoompan},setpts=PTS-STARTPTS[v{i}]"
        )

    # Concat all video streams + a null audio stream, then add real audio
    concat_inputs = "".join(f"[v{i}]" for i in range(num_frames))
    filter_parts.append(f"{concat_inputs}concat=n={num_frames}:v=1:a=0[vout]")
    if drawtext_filter:
        filter_parts[-1] = f"{concat_inputs}concat=n={num_frames}:v=1:a=0[vtmp];[vtmp]{drawtext_filter.lstrip(',')}[vout]"

    filter_complex = ";".join(filter_parts)

    cmd = (
        input_args
        + ["-i", effective_audio]
        + [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", f"{num_frames}:a",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-c:a", "aac",
            "-b:a", "128k",
            "-t", str(duration_seconds),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-y",
            output_path,
        ]
    )
    cmd = ["ffmpeg"] + cmd

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
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
                assembly_status="failed",
                assembly_engine="ffmpeg",
                error=f"FFmpeg sequence failed (rc={result.returncode}): {result.stderr[:800]}",
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
            assembly_status="failed",
            assembly_engine="ffmpeg",
            error="FFmpeg sequence timed out after 600s.",
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
            assembly_status="failed",
            assembly_engine="ffmpeg",
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
        assembly_status="success",
        assembly_engine="ffmpeg",
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
    Return a path to a 1080x1920 placeholder PNG (black background with
    SignalForge label). Created using FFmpeg lavfi — no external downloads.
    """
    os.makedirs("/tmp/signalforge_renders", exist_ok=True)
    path = f"/tmp/signalforge_renders/placeholder_{render_id}.png"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=#1e1b4b:s=1080x1920:d=1",
                "-vf", "drawtext=text='SignalForge Placeholder':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
                "-frames:v", "1",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
    except Exception:
        pass
    return path


def generate_test_tone(
    duration_seconds: float = 30.0,
    output_path: str = "",
    frequency: int = 440,
) -> str:
    """
    Generate a safe local sine-wave WAV test tone using FFmpeg lavfi.

    Used when no source_audio_path is provided for a render. This never
    downloads external media and never calls any social platform API.

    Returns the path to the generated WAV file, or empty string on failure.
    """
    os.makedirs("/tmp/signalforge_renders", exist_ok=True)
    if not output_path:
        output_path = f"/tmp/signalforge_renders/testtone_{uuid.uuid4()}.wav"
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"sine=frequency={frequency}:duration={duration_seconds}",
                "-ar", "44100",
                "-ac", "1",
                output_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return output_path
    except Exception:
        pass
    return ""


def ffmpeg_diagnostics() -> dict:
    """
    Return FFmpeg availability diagnostics.

    Returns:
        {
            "ffmpeg_available": bool,
            "ffmpeg_path": str,
            "ffmpeg_version": str,
            "ffmpeg_enabled": bool,
        }
    """
    import shutil
    ffmpeg_path = shutil.which("ffmpeg") or ""
    version = ""
    available = bool(ffmpeg_path)
    if available:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
            version = first_line[:120]
        except Exception:
            available = False
    return {
        "ffmpeg_available": available,
        "ffmpeg_path": ffmpeg_path,
        "ffmpeg_version": version,
        "ffmpeg_enabled": _env_enabled(os.getenv("FFMPEG_ENABLED", "false")),
    }
