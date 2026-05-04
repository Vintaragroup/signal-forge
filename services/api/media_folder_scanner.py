"""
Media Folder Scanner — SignalForge v10.4

Scans a local folder (including Google Drive / Dropbox desktop sync folders)
for supported media files and registers each as a media_intake_record.

Safety guarantees
-----------------
* Only reads local filesystem metadata — no uploads, no remote API calls.
* No files are deleted or modified.
* No shell command interpolation — path handling is pure Python.
* Duration extraction uses ffprobe via a safe command array (no shell=True).
* All produced records carry simulation_only=True, outbound_actions_taken=0.
* All discovered media starts in ingestion_status='discovered' (review-gated).

Env vars
--------
``FFPROBE_PATH``  — override path to ffprobe binary (default: 'ffprobe').
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".mov", ".m4v", ".mp3", ".wav", ".m4a"}
)

_AUDIO_EXTENSIONS: frozenset[str] = frozenset({".mp3", ".wav", ".m4a"})
_VIDEO_EXTENSIONS: frozenset[str] = frozenset({".mp4", ".mov", ".m4v"})

_MAX_PATH_LENGTH = 4096
_HASH_CHUNK_SIZE = 65536  # 64 KB


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass
class ScannedFile:
    """Metadata for a single discovered media file."""

    filename: str = ""
    absolute_path: str = ""
    size_bytes: int = 0
    modified_at: Optional[datetime] = None
    media_type: str = ""           # "video" | "audio"
    extension: str = ""
    duration_seconds: Optional[float] = None
    file_hash: Optional[str] = None
    ingestion_source: str = "local_folder"
    ingestion_status: str = "discovered"   # "discovered" | "registered" | "failed"
    ingestion_notes: str = ""
    simulation_only: bool = True
    outbound_actions_taken: int = 0


@dataclass
class ScanResult:
    """Aggregate result of a folder scan."""

    workspace_slug: str = ""
    client_id: str = ""
    folder_path: str = ""
    source_label: str = ""
    discovered_count: int = 0
    registered_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    items: list[ScannedFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    simulation_only: bool = True
    outbound_actions_taken: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_ffprobe_duration(path: str) -> Optional[float]:
    """
    Return duration_seconds from ffprobe, or None if unavailable/failed.

    Uses a command array — never shell=True — to prevent injection.
    """
    ffprobe_bin = os.getenv("FFPROBE_PATH", "ffprobe")
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        raw = result.stdout.strip()
        if raw:
            return float(raw)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _compute_file_hash(path: str) -> Optional[str]:
    """Return SHA-256 hex digest of file, or None on error."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(_HASH_CHUNK_SIZE):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _classify_media_type(ext: str) -> str:
    if ext in _AUDIO_EXTENSIONS:
        return "audio"
    if ext in _VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def _validate_folder_path(folder_path: str) -> tuple[bool, str]:
    """Return (valid, error_message)."""
    if not folder_path:
        return False, "folder_path is required"
    if len(folder_path) > _MAX_PATH_LENGTH:
        return False, f"folder_path exceeds maximum length ({_MAX_PATH_LENGTH})"
    p = Path(folder_path)
    if not p.exists():
        return False, f"Folder not found: {folder_path}"
    if not p.is_dir():
        return False, f"Path is not a directory: {folder_path}"
    return True, ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_media_folder(
    workspace_slug: str,
    client_id: str,
    folder_path: str,
    source_label: str = "",
    ingestion_source: str = "local_folder",
    compute_hashes: bool = False,
    existing_paths: Optional[set[str]] = None,
    existing_hashes: Optional[set[str]] = None,
) -> ScanResult:
    """
    Scan *folder_path* for supported media files and return a ScanResult.

    Parameters
    ----------
    workspace_slug
        Workspace this scan belongs to.
    client_id
        Client this media belongs to.
    folder_path
        Absolute or relative path to the folder to scan (can be a Google Drive
        or Dropbox synced folder on the local filesystem).
    source_label
        Optional human label, e.g. "Google Drive – JM Content".
    ingestion_source
        One of: ``local_folder``, ``google_drive_sync``, ``dropbox_sync``.
    compute_hashes
        If True, compute SHA-256 for each file.  Can be slow for large files.
    existing_paths
        Set of absolute paths already registered — used to skip duplicates.
    existing_hashes
        Set of SHA-256 hashes already registered — used to skip duplicates.

    Returns
    -------
    ScanResult
        All discovered files plus aggregate counts.  simulation_only is always
        True.  No external calls are made.
    """
    existing_paths = existing_paths or set()
    existing_hashes = existing_hashes or set()

    result = ScanResult(
        workspace_slug=workspace_slug,
        client_id=client_id,
        folder_path=folder_path,
        source_label=source_label,
        simulation_only=True,
        outbound_actions_taken=0,
    )

    valid, err = _validate_folder_path(folder_path)
    if not valid:
        result.errors.append(err)
        result.failed_count += 1
        return result

    folder = Path(folder_path).resolve()

    for file_path in sorted(folder.rglob("*")):
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            result.skipped_count += 1
            continue

        abs_path = str(file_path)

        # Duplicate path check
        if abs_path in existing_paths:
            sf = ScannedFile(
                filename=file_path.name,
                absolute_path=abs_path,
                extension=ext,
                media_type=_classify_media_type(ext),
                ingestion_source=ingestion_source,
                ingestion_status="registered",
                ingestion_notes="skipped: already registered by path",
                simulation_only=True,
                outbound_actions_taken=0,
            )
            result.skipped_count += 1
            result.items.append(sf)
            continue

        # File stat
        try:
            stat = file_path.stat()
            size_bytes = stat.st_size
            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        except OSError as exc:
            sf = ScannedFile(
                filename=file_path.name,
                absolute_path=abs_path,
                extension=ext,
                media_type=_classify_media_type(ext),
                ingestion_source=ingestion_source,
                ingestion_status="failed",
                ingestion_notes=f"stat error: {exc}",
                simulation_only=True,
                outbound_actions_taken=0,
            )
            result.failed_count += 1
            result.items.append(sf)
            continue

        # Optional hash
        file_hash: Optional[str] = None
        if compute_hashes:
            file_hash = _compute_file_hash(abs_path)
            if file_hash and file_hash in existing_hashes:
                sf = ScannedFile(
                    filename=file_path.name,
                    absolute_path=abs_path,
                    size_bytes=size_bytes,
                    modified_at=modified_at,
                    extension=ext,
                    media_type=_classify_media_type(ext),
                    file_hash=file_hash,
                    ingestion_source=ingestion_source,
                    ingestion_status="registered",
                    ingestion_notes="skipped: already registered by hash",
                    simulation_only=True,
                    outbound_actions_taken=0,
                )
                result.skipped_count += 1
                result.items.append(sf)
                continue

        # Duration via ffprobe (best-effort)
        duration = _safe_ffprobe_duration(abs_path)

        sf = ScannedFile(
            filename=file_path.name,
            absolute_path=abs_path,
            size_bytes=size_bytes,
            modified_at=modified_at,
            media_type=_classify_media_type(ext),
            extension=ext,
            duration_seconds=duration,
            file_hash=file_hash,
            ingestion_source=ingestion_source,
            ingestion_status="discovered",
            ingestion_notes="",
            simulation_only=True,
            outbound_actions_taken=0,
        )
        result.discovered_count += 1
        result.items.append(sf)

    return result
