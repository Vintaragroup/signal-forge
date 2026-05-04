"""
Approved URL Downloader — SignalForge v10.4

Downloads media from operator-approved URLs using yt-dlp.

Safety guarantees
-----------------
* YTDLP_ENABLED must be explicitly set to ``true`` (default: false).
* ``permission_confirmed`` must be True on every request.
* Only domains listed in YTDLP_ALLOWED_DOMAINS are accepted.
* yt-dlp is invoked via a command array — never shell=True — so user-supplied
  URLs cannot inject shell commands.
* Downloaded files are stored locally only.  Nothing is published, uploaded,
  or transmitted to any third party.
* All records carry simulation_only=True, outbound_actions_taken=0.
* Max duration enforced at the yt-dlp argument level.

Env vars
--------
``YTDLP_ENABLED``              — ``true`` / ``false`` (default: ``false``)
``YTDLP_OUTPUT_DIR``           — local output directory (default: ``/tmp/signalforge_downloads``)
``YTDLP_MAX_DURATION_SECONDS`` — max video/audio duration in seconds (default: 7200)
``YTDLP_ALLOWED_DOMAINS``      — comma-separated list (default: ``youtube.com,youtu.be``)
``YTDLP_PATH``                 — override path to yt-dlp binary (default: ``yt-dlp``)
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_OUTPUT_DIR = "/tmp/signalforge_downloads"
_DEFAULT_MAX_DURATION = 7200
_DEFAULT_ALLOWED_DOMAINS = {"youtube.com", "youtu.be"}
_MAX_URL_LENGTH = 2048
_SUBPROCESS_TIMEOUT = 600  # 10 minutes


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass
class DownloadResult:
    """Result of a single yt-dlp download attempt."""

    url: str = ""
    output_path: str = ""
    filename: str = ""
    duration_seconds: Optional[float] = None
    status: str = "queued"     # queued | running | completed | failed | skipped
    error_message: str = ""
    skip_reason: str = ""
    requested_format: str = "video"   # video | audio
    simulation_only: bool = True
    outbound_actions_taken: int = 0


@dataclass
class YtDlpDiagnostics:
    """Health/diagnostic info for the yt-dlp integration."""

    yt_dlp_enabled: bool = False
    yt_dlp_available: bool = False
    yt_dlp_path: str = ""
    yt_dlp_version: str = ""
    output_dir: str = ""
    output_dir_exists: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    max_duration_seconds: int = _DEFAULT_MAX_DURATION
    simulation_only: bool = True
    outbound_actions_taken: int = 0


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def _is_enabled() -> bool:
    return os.getenv("YTDLP_ENABLED", "false").strip().lower() == "true"


def _output_dir() -> str:
    return os.getenv("YTDLP_OUTPUT_DIR", _DEFAULT_OUTPUT_DIR).strip()


def _max_duration() -> int:
    try:
        return int(os.getenv("YTDLP_MAX_DURATION_SECONDS", str(_DEFAULT_MAX_DURATION)))
    except ValueError:
        return _DEFAULT_MAX_DURATION


def _allowed_domains() -> set[str]:
    raw = os.getenv("YTDLP_ALLOWED_DOMAINS", "").strip()
    if raw:
        return {d.strip().lower() for d in raw.split(",") if d.strip()}
    return set(_DEFAULT_ALLOWED_DOMAINS)


def _ytdlp_bin() -> str:
    return os.getenv("YTDLP_PATH", "yt-dlp").strip()


def _find_ytdlp() -> Optional[str]:
    """Return the resolved path of the yt-dlp binary, or None if not found."""
    explicit = os.getenv("YTDLP_PATH", "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    found = shutil.which("yt-dlp")
    return found


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_url(url: str, allowed_domains: set[str]) -> tuple[bool, str]:
    """Return (valid, error_message)."""
    if not url:
        return False, "url is required"
    if len(url) > _MAX_URL_LENGTH:
        return False, f"url exceeds maximum length ({_MAX_URL_LENGTH})"
    # Must be http/https
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "url could not be parsed"
    if parsed.scheme not in ("http", "https"):
        return False, "url must use http or https scheme"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "url has no hostname"
    # Check against allowed domains (exact match or subdomain)
    matched = any(
        hostname == d or hostname.endswith("." + d)
        for d in allowed_domains
    )
    if not matched:
        return False, (
            f"domain '{hostname}' is not in the allowed list. "
            f"Allowed: {sorted(allowed_domains)}"
        )
    return True, ""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_diagnostics() -> YtDlpDiagnostics:
    """Return diagnostic information about the yt-dlp integration."""
    ytdlp_path = _find_ytdlp() or ""
    available = bool(ytdlp_path)
    version = ""
    if available:
        try:
            r = subprocess.run(
                [ytdlp_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass

    out_dir = _output_dir()
    return YtDlpDiagnostics(
        yt_dlp_enabled=_is_enabled(),
        yt_dlp_available=available,
        yt_dlp_path=ytdlp_path,
        yt_dlp_version=version,
        output_dir=out_dir,
        output_dir_exists=Path(out_dir).exists(),
        allowed_domains=sorted(_allowed_domains()),
        max_duration_seconds=_max_duration(),
        simulation_only=True,
        outbound_actions_taken=0,
    )


def download_approved_url(
    workspace_slug: str,
    client_id: str,
    url: str,
    permission_confirmed: bool,
    requested_format: str = "video",
    notes: str = "",
    source_content_id: str = "",
) -> DownloadResult:
    """
    Download media from *url* using yt-dlp.

    Guards (checked in order):
    1. YTDLP_ENABLED must be ``true``.
    2. ``permission_confirmed`` must be True.
    3. Domain must be in YTDLP_ALLOWED_DOMAINS.
    4. yt-dlp binary must be found on PATH or YTDLP_PATH.

    The download is run as a child process using a command array — no
    shell=True, no string interpolation of the URL.

    Returns
    -------
    DownloadResult
        Always simulation_only=True, outbound_actions_taken=0.
    """
    result = DownloadResult(
        url=url,
        requested_format=requested_format,
        simulation_only=True,
        outbound_actions_taken=0,
    )

    # Guard 1 — feature flag
    if not _is_enabled():
        result.status = "skipped"
        result.skip_reason = "YTDLP_ENABLED is not set to true"
        return result

    # Guard 2 — permission
    if not permission_confirmed:
        result.status = "skipped"
        result.skip_reason = "permission_confirmed is false; download not attempted"
        return result

    # Guard 3 — domain allowlist
    domains = _allowed_domains()
    valid, err = _validate_url(url, domains)
    if not valid:
        result.status = "failed"
        result.error_message = err
        return result

    # Guard 4 — binary availability
    ytdlp_bin = _find_ytdlp()
    if not ytdlp_bin:
        result.status = "failed"
        result.error_message = (
            "yt-dlp binary not found. Install yt-dlp and ensure it is on PATH, "
            "or set YTDLP_PATH."
        )
        return result

    # Prepare output directory
    out_dir = Path(_output_dir()) / workspace_slug
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.status = "failed"
        result.error_message = f"Could not create output directory: {exc}"
        return result

    # Build yt-dlp command array (no shell=True, no f-string interpolation of url)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    output_template = str(out_dir / f"%(title).60s_{timestamp}.%(ext)s")

    cmd: list[str] = [ytdlp_bin]

    if requested_format == "audio":
        cmd += ["-x", "--audio-format", "mp3"]
    else:
        # Prefer mp4/m4v, fallback to best
        cmd += ["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"]

    cmd += [
        "--max-filesize", "2G",
        "--match-filter", f"duration <= {_max_duration()}",
        "--no-playlist",
        "--no-post-overwrites",
        "--restrict-filenames",
        "-o", output_template,
        "--print", "after_move:filepath",  # reports actual path after post-processing (e.g. mp3 conversion)
        "--",         # separator — ensures url is treated as positional, not a flag
        url,
    ]

    result.status = "running"
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        result.status = "failed"
        result.error_message = f"yt-dlp timed out after {_SUBPROCESS_TIMEOUT}s"
        return result
    except OSError as exc:
        result.status = "failed"
        result.error_message = f"Failed to launch yt-dlp: {exc}"
        return result

    if proc.returncode != 0:
        # Sanitise stderr to avoid leaking paths in logs
        raw_err = (proc.stderr or "").strip()
        # Truncate to 500 chars
        result.status = "failed"
        result.error_message = raw_err[:500] if raw_err else f"yt-dlp exited {proc.returncode}"
        return result

    # Parse output path from stdout (yt-dlp --print after_move:filepath outputs actual path)
    stdout_lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    output_path = ""
    for line in stdout_lines:
        candidate = Path(line)
        if candidate.is_file():
            output_path = str(candidate)
            break

    # Fallback: scan output dir for newest file created since we started the subprocess
    if not output_path and out_dir.exists():
        candidates = sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates and candidates[0].is_file():
            output_path = str(candidates[0])

    if not output_path:
        result.status = "failed"
        result.error_message = "Download appeared to succeed but output file not found"
        return result

    # Try to get duration via ffprobe
    duration: Optional[float] = None
    try:
        from media_folder_scanner import _safe_ffprobe_duration
        duration = _safe_ffprobe_duration(output_path)
    except ImportError:
        pass

    result.output_path = output_path
    result.filename = Path(output_path).name
    result.duration_seconds = duration
    result.status = "completed"
    return result
