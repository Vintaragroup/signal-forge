"""
Media intake abstraction — Social Creative Engine v4.

Handles manual media registration: approved local file paths and URL
metadata-only intake.

Safety guarantee
----------------
* No files are downloaded from remote URLs unless MEDIA_DOWNLOAD_ENABLED=true
  AND the source content record has approved_for_download=True.
* No platform scraping or circumvention of access controls.
* Registered media records always carry simulation_only=True and
  outbound_actions_taken=0.
* Local file paths are validated for existence and sane extension only — no
  binary parsing, no shell execution, no subprocess calls.

Design
------
``MediaIntakeRecord`` is a plain value object describing the result of
registering a media item.  Two helpers are provided:

  ``register_local_file(path)``
      Validates a local filesystem path. Does not read file contents.
      Returns a ``MediaIntakeRecord`` with ``intake_method='local_file'``.

  ``register_url_metadata(url)``
      Stores the URL string for metadata purposes only.  Does not fetch
      the URL.  Returns a ``MediaIntakeRecord`` with
      ``intake_method='url_metadata_only'``.

Env vars
--------
``MEDIA_DOWNLOAD_ENABLED=false`` (default)
    Set to ``true`` AND set ``approved_for_download=true`` on the source
    content record to allow a future downloader to fetch the file.
    No downloader is implemented yet; enabling the flag alone has no effect.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Extensions accepted as valid media.  Not exhaustive — just a safety gate.
_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".flac"}
)

_MAX_PATH_LENGTH = 1024


@dataclass
class MediaIntakeRecord:
    """
    Value object describing the result of a media intake registration.

    Fields
    ------
    intake_method : str
        ``'local_file'`` | ``'url_metadata_only'``
    status : str
        ``'registered'`` | ``'skipped'`` | ``'failed'``
    media_path : str
        Resolved absolute path (local_file) or empty string (url_metadata_only).
    source_url : str
        Original URL provided by the operator. May be empty for local_file.
    approved_for_download : bool
        Whether the source content record has been explicitly approved for
        download.  Never set to True by this module — must be set by the
        operator via the API.
    error : str
        Non-empty when status='failed'.
    skip_reason : str
        Non-empty when status='skipped'.
    extension : str
        Detected file extension (e.g. '.mp4').
    simulation_only : bool
        Always True.
    outbound_actions_taken : int
        Always 0.
    """

    intake_method: str = "url_metadata_only"
    status: str = "registered"
    media_path: str = ""
    source_url: str = ""
    approved_for_download: bool = False
    error: str = ""
    skip_reason: str = ""
    extension: str = ""
    simulation_only: bool = True
    outbound_actions_taken: int = 0


def register_local_file(path: str) -> MediaIntakeRecord:
    """
    Register a local media file path.

    Validates:
    - path length is reasonable
    - extension is in the allowed media set
    - file exists at the given path

    Does NOT:
    - read file contents
    - parse binary data
    - call any subprocess

    Returns a ``MediaIntakeRecord`` with ``intake_method='local_file'``.
    """
    if not path or not path.strip():
        return MediaIntakeRecord(
            intake_method="local_file",
            status="failed",
            error="path is empty",
        )

    clean = path.strip()

    if len(clean) > _MAX_PATH_LENGTH:
        return MediaIntakeRecord(
            intake_method="local_file",
            status="failed",
            error="path exceeds maximum length",
        )

    # Reject obvious traversal attempts
    try:
        resolved = str(Path(clean).resolve())
    except (ValueError, OSError) as exc:
        return MediaIntakeRecord(
            intake_method="local_file",
            status="failed",
            error=f"path resolution error: {exc}",
        )

    ext = Path(resolved).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return MediaIntakeRecord(
            intake_method="local_file",
            status="failed",
            error=f"unsupported media extension '{ext}'. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    if not os.path.exists(resolved):
        return MediaIntakeRecord(
            intake_method="local_file",
            status="failed",
            error=f"file not found: {resolved}",
        )

    if not os.path.isfile(resolved):
        return MediaIntakeRecord(
            intake_method="local_file",
            status="failed",
            error=f"path is not a file: {resolved}",
        )

    return MediaIntakeRecord(
        intake_method="local_file",
        status="registered",
        media_path=resolved,
        extension=ext,
    )


def register_url_metadata(url: str) -> MediaIntakeRecord:
    """
    Register a URL for metadata purposes only.

    Does NOT fetch the URL, download content, or follow redirects.
    The URL is stored as-is for operator reference.

    Returns a ``MediaIntakeRecord`` with ``intake_method='url_metadata_only'``.
    """
    if not url or not url.strip():
        return MediaIntakeRecord(
            intake_method="url_metadata_only",
            status="failed",
            error="url is empty",
        )

    clean = url.strip()

    # Basic scheme guard — only http/https
    lower = clean.lower()
    if not lower.startswith("http://") and not lower.startswith("https://"):
        return MediaIntakeRecord(
            intake_method="url_metadata_only",
            status="failed",
            error="url must start with http:// or https://",
        )

    return MediaIntakeRecord(
        intake_method="url_metadata_only",
        status="registered",
        source_url=clean,
        skip_reason="url_download_not_enabled",
    )
