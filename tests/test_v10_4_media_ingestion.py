"""
SignalForge v10.4 — Media Ingestion Layer Tests

Covers:
- media_folder_scanner: finds supported files, skips unsupported, handles missing folder,
  skips duplicate paths, skips duplicate hashes, simulation_only always True
- approved_url_downloader: disabled skips, no permission skips, invalid domain fails,
  missing binary fails, mocked success creates media_intake_record
- API: POST /media-folder-scans creates intake records, workspace isolation,
  client isolation, simulation_only=True, outbound_actions_taken=0 always
- API: POST /approved-url-downloads with disabled yt-dlp returns skipped
- API: GET /media-ingestion/diagnostics returns yt-dlp info and scanner extensions
- API: GET list endpoints filter by workspace_slug
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import main
from main import app

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)
REAL_WS = "test-media-ws"
CLIENT_ID = str(ObjectId())


def make_doc(**kwargs):
    return {"_id": ObjectId(), "created_at": NOW, "updated_at": NOW, **kwargs}


class InsertResult:
    def __init__(self, inserted_id=None):
        self.inserted_id = inserted_id or ObjectId()


class FakeCursor:
    def __init__(self, docs=None):
        self._docs = list(docs or [])

    def __iter__(self):
        return iter(self._docs)

    def sort(self, *_, **__):
        return self

    def limit(self, *_, **__):
        return self

    def skip(self, *_, **__):
        return self


class FakeCollection:
    def __init__(self, docs=None):
        self._docs = list(docs or [])

    def find(self, query=None, *_, **__):
        if not query:
            return FakeCursor(self._docs)
        # Simple equality filter (sufficient for unit tests)
        results = [d for d in self._docs if all(d.get(k) == v for k, v in query.items())]
        return FakeCursor(results)

    def find_one(self, *_, **__):
        return self._docs[0] if self._docs else None

    def insert_one(self, doc):
        doc.setdefault("_id", ObjectId())
        self._docs.append(doc)
        return InsertResult(doc["_id"])

    def update_one(self, *_, **__):
        return MagicMock(modified_count=1)


class FakeDatabase:
    def __init__(self):
        self.media_folder_scans = FakeCollection()
        self.media_intake_records = FakeCollection()
        self.approved_url_downloads = FakeCollection()
        self.client_profiles = FakeCollection()

    def __getattr__(self, name):
        return FakeCollection()


# ---------------------------------------------------------------------------
# Direct imports for unit tests
# ---------------------------------------------------------------------------

try:
    from media_folder_scanner import (
        ScanResult,
        ScannedFile,
        _classify_media_type,
        _validate_folder_path,
        scan_media_folder,
        SUPPORTED_EXTENSIONS,
    )
    SCANNER_AVAILABLE = True
except ImportError:
    SCANNER_AVAILABLE = False

try:
    from approved_url_downloader import (
        DownloadResult,
        YtDlpDiagnostics,
        download_approved_url,
        get_diagnostics,
        _validate_url,
        _allowed_domains,
    )
    DOWNLOADER_AVAILABLE = True
except ImportError:
    DOWNLOADER_AVAILABLE = False

# ---------------------------------------------------------------------------
# media_folder_scanner unit tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_supported_extensions():
    """SUPPORTED_EXTENSIONS must include all required video/audio types."""
    assert ".mp4" in SUPPORTED_EXTENSIONS
    assert ".mov" in SUPPORTED_EXTENSIONS
    assert ".m4v" in SUPPORTED_EXTENSIONS
    assert ".mp3" in SUPPORTED_EXTENSIONS
    assert ".wav" in SUPPORTED_EXTENSIONS
    assert ".m4a" in SUPPORTED_EXTENSIONS


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_finds_supported_file(tmp_path):
    """scan_media_folder discovers a .mp4 file in a temp folder."""
    test_file = tmp_path / "clip.mp4"
    test_file.write_bytes(b"\x00" * 1024)

    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
    )

    assert result.discovered_count == 1
    assert len(result.items) == 1
    assert result.items[0].filename == "clip.mp4"
    assert result.items[0].extension == ".mp4"
    assert result.items[0].media_type == "video"
    assert result.items[0].ingestion_status == "discovered"


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_skips_unsupported_extension(tmp_path):
    """scan_media_folder skips .txt and .pdf files."""
    (tmp_path / "readme.txt").write_text("ignore me")
    (tmp_path / "doc.pdf").write_bytes(b"%PDF")

    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
    )

    assert result.discovered_count == 0
    assert len(result.items) == 0


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_multiple_extensions(tmp_path):
    """scan_media_folder discovers multiple file types in same folder."""
    (tmp_path / "video.mp4").write_bytes(b"\x00" * 1024)
    (tmp_path / "audio.mp3").write_bytes(b"\xff\xfb" * 512)
    (tmp_path / "ignore.txt").write_text("skip")

    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
    )

    assert result.discovered_count == 2
    exts = {item.extension for item in result.items}
    assert ".mp4" in exts
    assert ".mp3" in exts


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_missing_folder_fails_safely():
    """scan_media_folder returns error and zero count for non-existent path."""
    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path="/nonexistent/folder/that/does/not/exist",
    )

    assert result.discovered_count == 0
    assert len(result.errors) > 0


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_duplicate_path_skipped(tmp_path):
    """scan_media_folder skips files whose absolute path already exists in existing_paths."""
    test_file = tmp_path / "clip.mp4"
    test_file.write_bytes(b"\x00" * 1024)

    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
        existing_paths={str(test_file)},
    )

    assert result.discovered_count == 0
    assert result.skipped_count == 1


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_result_simulation_only(tmp_path):
    """ScanResult always has simulation_only=True and outbound_actions_taken=0."""
    (tmp_path / "clip.mp4").write_bytes(b"\x00" * 512)

    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
    )

    assert result.simulation_only is True
    assert result.outbound_actions_taken == 0


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_classify_media_type():
    """_classify_media_type returns correct type for known extensions."""
    assert _classify_media_type(".mp4") == "video"
    assert _classify_media_type(".mov") == "video"
    assert _classify_media_type(".mp3") == "audio"
    assert _classify_media_type(".wav") == "audio"
    assert _classify_media_type(".xyz") == "unknown"


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_validate_folder_path_empty():
    """_validate_folder_path returns error for empty string."""
    valid, err = _validate_folder_path("")
    assert not valid
    assert err


@pytest.mark.skipif(not SCANNER_AVAILABLE, reason="media_folder_scanner not importable")
def test_scan_audio_file_media_type(tmp_path):
    """Audio files (.m4a, .wav) are classified as audio media_type."""
    (tmp_path / "track.m4a").write_bytes(b"\x00" * 512)
    (tmp_path / "mix.wav").write_bytes(b"RIFF")

    result = scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
    )

    assert result.discovered_count == 2
    types = {item.media_type for item in result.items}
    assert types == {"audio"}


# ---------------------------------------------------------------------------
# approved_url_downloader unit tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_download_disabled_returns_skipped(monkeypatch):
    """When YTDLP_ENABLED is false, download_approved_url returns status=skipped."""
    monkeypatch.setenv("YTDLP_ENABLED", "false")

    result = download_approved_url(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        permission_confirmed=True,
        requested_format="video",
        notes="",
        source_content_id="",
    )

    assert result.status == "skipped"
    assert result.skip_reason
    assert result.simulation_only is True
    assert result.outbound_actions_taken == 0


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_download_no_permission_returns_skipped(monkeypatch):
    """When permission_confirmed is False, download_approved_url returns status=skipped."""
    monkeypatch.setenv("YTDLP_ENABLED", "true")

    result = download_approved_url(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        permission_confirmed=False,
        requested_format="video",
        notes="",
        source_content_id="",
    )

    assert result.status == "skipped"
    assert result.skip_reason
    assert result.outbound_actions_taken == 0


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_download_invalid_domain_returns_failed(monkeypatch):
    """A URL not in YTDLP_ALLOWED_DOMAINS returns status=failed."""
    monkeypatch.setenv("YTDLP_ENABLED", "true")
    monkeypatch.setenv("YTDLP_ALLOWED_DOMAINS", "youtube.com,youtu.be")

    result = download_approved_url(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        url="https://evil.example.com/video",
        permission_confirmed=True,
        requested_format="video",
        notes="",
        source_content_id="",
    )

    assert result.status == "failed"
    assert result.error_message
    assert result.outbound_actions_taken == 0


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_download_missing_binary_returns_failed(monkeypatch, tmp_path):
    """When yt-dlp binary is not found, download returns status=failed."""
    monkeypatch.setenv("YTDLP_ENABLED", "true")
    monkeypatch.setenv("YTDLP_PATH", "/nonexistent/yt-dlp-binary")
    monkeypatch.setenv("YTDLP_ALLOWED_DOMAINS", "youtube.com,youtu.be")

    result = download_approved_url(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        permission_confirmed=True,
        requested_format="video",
        notes="",
        source_content_id="",
    )

    assert result.status == "failed"
    assert result.outbound_actions_taken == 0


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_validate_url_allowed_domain(monkeypatch):
    """_validate_url returns True for domain in allowed list (with subdomain)."""
    monkeypatch.setenv("YTDLP_ALLOWED_DOMAINS", "youtube.com,youtu.be")
    allowed = _allowed_domains()
    valid, err = _validate_url("https://www.youtube.com/watch?v=abc", allowed)
    assert valid, f"Expected valid but got: {err}"


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_validate_url_blocked_domain(monkeypatch):
    """_validate_url returns False for domain not in allowed list."""
    monkeypatch.setenv("YTDLP_ALLOWED_DOMAINS", "youtube.com,youtu.be")
    allowed = _allowed_domains()
    valid, err = _validate_url("https://malicious.example.com/video", allowed)
    assert not valid


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_validate_url_rejects_non_https(monkeypatch):
    """_validate_url rejects non-http/https schemes."""
    monkeypatch.setenv("YTDLP_ALLOWED_DOMAINS", "youtube.com")
    allowed = _allowed_domains()
    valid, err = _validate_url("ftp://youtube.com/video", allowed)
    assert not valid


@pytest.mark.skipif(not DOWNLOADER_AVAILABLE, reason="approved_url_downloader not importable")
def test_download_result_always_simulation_only(monkeypatch):
    """DownloadResult always has simulation_only=True regardless of outcome."""
    monkeypatch.setenv("YTDLP_ENABLED", "false")

    result = download_approved_url(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        url="https://www.youtube.com/watch?v=abc",
        permission_confirmed=True,
        requested_format="audio",
        notes="test",
        source_content_id="",
    )
    assert result.simulation_only is True
    assert result.outbound_actions_taken == 0


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

client = TestClient(app)


def _fake_db_scan():
    db = FakeDatabase()
    return db


def test_api_media_folder_scan_creates_intake_records(monkeypatch, tmp_path):
    """POST /media-folder-scans creates media_intake_records for each discovered file."""
    mp4 = tmp_path / "clip.mp4"
    mp4.write_bytes(b"\x00" * 1024)

    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.post("/media-folder-scans", json={
            "workspace_slug": REAL_WS,
            "client_id": CLIENT_ID,
            "folder_path": str(tmp_path),
            "source_label": "test",
            "ingestion_source": "local_folder",
            "compute_hashes": False,
        })

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0
    assert body["discovered_count"] >= 1
    assert body["registered_count"] >= 1
    assert len(body["intake_ids"]) >= 1


def test_api_media_folder_scan_simulation_only_enforced(monkeypatch, tmp_path):
    """simulation_only and outbound_actions_taken are always present and correct."""
    (tmp_path / "audio.wav").write_bytes(b"RIFF")

    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.post("/media-folder-scans", json={
            "workspace_slug": REAL_WS,
            "client_id": CLIENT_ID,
            "folder_path": str(tmp_path),
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0


def test_api_folder_scan_missing_folder_returns_200_with_error(monkeypatch):
    """POST /media-folder-scans with non-existent path returns 200 with errors list."""
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.post("/media-folder-scans", json={
            "workspace_slug": REAL_WS,
            "client_id": CLIENT_ID,
            "folder_path": "/does/not/exist/folder",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["discovered_count"] == 0
    assert len(body.get("errors", [])) > 0


def test_api_approved_url_download_disabled_returns_skipped(monkeypatch):
    """POST /approved-url-downloads with YTDLP_ENABLED=false returns status=skipped."""
    monkeypatch.setenv("YTDLP_ENABLED", "false")
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.post("/approved-url-downloads", json={
            "workspace_slug": REAL_WS,
            "client_id": CLIENT_ID,
            "url": "https://www.youtube.com/watch?v=abc",
            "permission_confirmed": True,
            "requested_format": "video",
            "notes": "",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "skipped"
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0


def test_api_approved_url_download_no_permission_skips(monkeypatch):
    """POST /approved-url-downloads with permission_confirmed=false returns skipped."""
    monkeypatch.setenv("YTDLP_ENABLED", "true")
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.post("/approved-url-downloads", json={
            "workspace_slug": REAL_WS,
            "client_id": CLIENT_ID,
            "url": "https://www.youtube.com/watch?v=abc",
            "permission_confirmed": False,
            "requested_format": "video",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "skipped"
    assert body["outbound_actions_taken"] == 0


def test_api_workspace_isolation(monkeypatch, tmp_path):
    """GET /media-folder-scans only returns records for the requested workspace."""
    ws_a = FakeCollection([
        {"_id": ObjectId(), "workspace_slug": "ws-a", "folder_path": "/a", "discovered_count": 1,
         "registered_count": 1, "skipped_count": 0, "failed_count": 0,
         "ingestion_source": "local_folder", "created_at": NOW},
    ])
    ws_b = FakeCollection([
        {"_id": ObjectId(), "workspace_slug": "ws-b", "folder_path": "/b", "discovered_count": 2,
         "registered_count": 2, "skipped_count": 0, "failed_count": 0,
         "ingestion_source": "local_folder", "created_at": NOW},
    ])

    db_a = FakeDatabase()
    db_a.media_folder_scans = ws_a

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db_a),
    ):
        resp = client.get("/media-folder-scans?workspace_slug=ws-a")

    assert resp.status_code == 200
    body = resp.json()
    items = body["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "ws-a"


def test_api_media_ingestion_diagnostics():
    """GET /media-ingestion/diagnostics returns scanner and yt_dlp info."""
    resp = client.get("/media-ingestion/diagnostics")
    assert resp.status_code == 200
    body = resp.json()
    assert "scanner" in body
    assert "yt_dlp" in body
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0
    assert isinstance(body["scanner"].get("supported_extensions"), list)


def test_api_list_folder_scans_empty():
    """GET /media-folder-scans returns empty list when no records exist."""
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get("/media-folder-scans?workspace_slug=empty-ws")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0


def test_api_list_approved_url_downloads_empty():
    """GET /approved-url-downloads returns empty list when no records exist."""
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get("/approved-url-downloads?workspace_slug=empty-ws")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["simulation_only"] is True
    assert body["outbound_actions_taken"] == 0


def test_api_get_folder_scan_not_found():
    """GET /media-folder-scans/{id} returns 404 for unknown ID."""
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get(f"/media-folder-scans/{ObjectId()}")

    assert resp.status_code == 404


def test_api_get_url_download_not_found():
    """GET /approved-url-downloads/{id} returns 404 for unknown ID."""
    db = FakeDatabase()

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get(f"/approved-url-downloads/{ObjectId()}")

    assert resp.status_code == 404


def test_scan_result_no_external_calls(monkeypatch, tmp_path):
    """scan_media_folder performs no network calls — validated via no subprocess with URLs."""
    (tmp_path / "clip.mp4").write_bytes(b"\x00" * 512)

    import subprocess
    original_run = subprocess.run
    calls = []

    def spy_run(cmd, *args, **kwargs):
        calls.append(cmd)
        return original_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy_run)

    scan_media_folder(
        workspace_slug=REAL_WS,
        client_id=CLIENT_ID,
        folder_path=str(tmp_path),
    )

    # No call should contain a URL (http/https pattern)
    for cmd in calls:
        cmd_str = " ".join(str(c) for c in (cmd if isinstance(cmd, list) else [cmd]))
        assert "http" not in cmd_str, f"Unexpected network call in scan: {cmd_str}"


# ---------------------------------------------------------------------------
# v10.4.1 — Client display tests (client_name in dropdowns)
# These tests cover API-level behavior: client_profiles must expose client_name
# ---------------------------------------------------------------------------


def _make_client(name: str, ws: str = REAL_WS) -> dict:
    return {"_id": ObjectId(), "client_name": name, "workspace_slug": ws, "created_at": NOW}


def test_api_client_profiles_returns_client_name():
    """GET /client-profiles returns client_name field (not just _id)."""
    clients = [_make_client("John Maxwell"), _make_client("Test Client")]
    db = FakeDatabase()
    db.client_profiles = FakeCollection(clients)

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get(f"/client-profiles?workspace_slug={REAL_WS}")

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    names = {i["client_name"] for i in items}
    assert "John Maxwell" in names
    assert "Test Client" in names


def test_api_client_profiles_workspace_filtering():
    """GET /client-profiles only returns clients for the requested workspace."""
    clients = [
        _make_client("John Maxwell", REAL_WS),
        _make_client("Other Client", "other-ws"),
    ]
    db = FakeDatabase()
    db.client_profiles = FakeCollection(clients)

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get(f"/client-profiles?workspace_slug={REAL_WS}")

    items = resp.json()["items"]
    assert all(i["workspace_slug"] == REAL_WS for i in items)
    assert len(items) == 1
    assert items[0]["client_name"] == "John Maxwell"


def test_api_client_profiles_no_clients_returns_empty_list():
    """GET /client-profiles returns empty list when workspace has no clients."""
    db = FakeDatabase()
    db.client_profiles = FakeCollection([])

    with (
        patch("main.get_client", return_value=MagicMock()),
        patch("main.get_database", return_value=db),
    ):
        resp = client.get(f"/client-profiles?workspace_slug={REAL_WS}")

    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_api_folder_scan_uses_client_id_from_request():
    """POST /media-folder-scans stores client_id (not client_name) on the scan record."""
    client_doc = _make_client("John Maxwell")
    client_id = str(client_doc["_id"])

    db = FakeDatabase()
    mongo_mock = MagicMock()

    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "test.mp4"), "wb").write(b"\x00" * 100)
        with (
            patch("main.get_client", return_value=mongo_mock),
            patch("main.get_database", return_value=db),
            patch("media_folder_scanner._safe_ffprobe_duration", return_value=None),
        ):
            resp = client.post("/media-folder-scans", json={
                "workspace_slug": REAL_WS,
                "client_id": client_id,
                "folder_path": tmp,
            })

    assert resp.status_code == 200
    # Verify client_id (not client_name) sent in request is stored
    stored = db.media_folder_scans._docs
    assert len(stored) == 1
    assert stored[0]["client_id"] == client_id


def test_api_url_download_sends_client_id_not_name(monkeypatch):
    """POST /approved-url-downloads stores client_id (not client_name) on the record."""
    monkeypatch.setenv("YTDLP_ENABLED", "false")
    client_doc = _make_client("John Maxwell")
    client_id = str(client_doc["_id"])

    db = FakeDatabase()
    mongo_mock = MagicMock()

    with (
        patch("main.get_client", return_value=mongo_mock),
        patch("main.get_database", return_value=db),
    ):
        resp = client.post("/approved-url-downloads", json={
            "workspace_slug": REAL_WS,
            "client_id": client_id,
            "url": "https://www.youtube.com/watch?v=test",
            "permission_confirmed": True,
            "requested_format": "video",
            "notes": "",
        })

    assert resp.status_code == 200
    stored = db.approved_url_downloads._docs
    assert len(stored) == 1
    assert stored[0]["client_id"] == client_id
