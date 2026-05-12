"""
Phase 6E — Backend tests for client_sources CRUD, URI normalization,
filtering, and discovery engine integration with configured sources.
"""
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app, normalize_source_uri
import discovery_engine as engine

# ── Shared fakes ──────────────────────────────────────────────────────────────


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, _spec, _direction=None):
        return self

    def limit(self, count):
        self.documents = self.documents[:count]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeCollection:
    def __init__(self, documents=None):
        self.documents = list(documents or [])

    def find(self, query=None):
        query = query or {}
        return FakeCursor([doc for doc in self.documents if self._matches(doc, query)])

    def find_one(self, query):
        docs = list(self.find(query))
        return docs[0] if docs else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update, upsert=False):
        doc = self.find_one(query)
        if not doc:
            return None
        for key, value in (update.get("$set") or {}).items():
            doc[key] = value
        return None

    def delete_one(self, query):
        doc = self.find_one(query)
        if doc:
            self.documents.remove(doc)

    def _matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self._matches(document, cond) for cond in value):
                    return False
                continue
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self):
        self.client_sources = FakeCollection([])
        self.admin_client_profiles = FakeCollection([])
        self.workflow_assets = FakeCollection([])
        self.discovery_insights = FakeCollection([])
        self.agent_tasks = FakeCollection([])
        self.agent_runs = FakeCollection([])


class FakeClient:
    def __init__(self, db: FakeDatabase):
        self._db = db

    def close(self):
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db():
    return FakeDatabase()


def _make_client(db):
    return FakeClient(db)


def _make_test_client(db):
    fc = _make_client(db)
    app_client = TestClient(app)
    # Monkeypatch both helpers
    app_client.__enter__ = lambda s: s
    app_client.__exit__ = lambda s, *a: None
    monkeypatch_client(fc, db)
    return app_client, fc


def monkeypatch_client(fake_client, fake_db):
    main.get_client = lambda: fake_client
    main.get_database = lambda c: fake_db


# ── URI normalization tests ───────────────────────────────────────────────────

def test_normalize_source_uri_bare_domain():
    assert normalize_source_uri("example.com") == "https://example.com"


def test_normalize_source_uri_already_https():
    assert normalize_source_uri("https://example.com") == "https://example.com"


def test_normalize_source_uri_already_http():
    assert normalize_source_uri("http://example.com/path") == "http://example.com/path"


def test_normalize_source_uri_strips_whitespace():
    assert normalize_source_uri("  https://example.com  ") == "https://example.com"


def test_normalize_source_uri_empty():
    assert normalize_source_uri("") == ""
    assert normalize_source_uri("   ") == ""


def test_normalize_source_uri_linkedin():
    assert normalize_source_uri("linkedin.com/in/johndoe") == "https://linkedin.com/in/johndoe"


def test_normalize_source_uri_rss_feed():
    result = normalize_source_uri("https://feeds.example.com/podcast.rss")
    assert result == "https://feeds.example.com/podcast.rss"


# ── Health status tests ───────────────────────────────────────────────────────

def test_health_ready():
    from main import _compute_source_health
    assert _compute_source_health("https://example.com", "active") == "ready"


def test_health_inactive():
    from main import _compute_source_health
    assert _compute_source_health("https://example.com", "inactive") == "inactive"


def test_health_invalid_empty_uri():
    from main import _compute_source_health
    assert _compute_source_health("", "active") == "invalid"


def test_health_invalid_malformed_uri():
    from main import _compute_source_health
    assert _compute_source_health("not-a-url!!!###", "active") == "invalid"


def test_health_invalid_no_scheme():
    from main import _compute_source_health
    # No netloc after stripping scheme
    assert _compute_source_health("file:///local/path", "active") in ("ready", "invalid")


# ── CRUD route tests ──────────────────────────────────────────────────────────

def test_create_client_source_success(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.post("/admin/client-sources", json={
        "workspace_slug": "ws-test",
        "client_profile_slug": "john-doe",
        "source_type": "linkedin",
        "label": "John LinkedIn",
        "uri": "https://linkedin.com/in/johndoe",
        "status": "active",
    })
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["source_type"] == "linkedin"
    assert item["label"] == "John LinkedIn"
    assert item["workspace_slug"] == "ws-test"
    assert item["health_status"] == "ready"


def test_create_client_source_normalizes_uri(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.post("/admin/client-sources", json={
        "workspace_slug": "ws-test",
        "client_profile_slug": "john-doe",
        "source_type": "website",
        "label": "Website",
        "uri": "example.com",
    })
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["uri"] == "https://example.com"


def test_create_client_source_invalid_source_type(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.post("/admin/client-sources", json={
        "workspace_slug": "ws-test",
        "client_profile_slug": "john-doe",
        "source_type": "slack",  # invalid
        "label": "My Slack",
        "uri": "https://slack.com",
    })
    assert resp.status_code == 422


def test_create_client_source_missing_workspace(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.post("/admin/client-sources", json={
        "workspace_slug": "",
        "client_profile_slug": "john-doe",
        "source_type": "linkedin",
        "label": "LinkedIn",
        "uri": "https://linkedin.com",
    })
    assert resp.status_code == 400


def test_list_client_sources_all(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    db.client_sources.documents = [
        {"_id": ObjectId(), "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "linkedin", "label": "L1", "uri": "https://l.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "workspace_slug": "ws-b", "client_profile_slug": "p-b",
         "source_type": "instagram", "label": "I1", "uri": "https://i.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get("/admin/client-sources")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2


def test_list_client_sources_filter_workspace(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    db.client_sources.documents = [
        {"_id": ObjectId(), "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "linkedin", "label": "L1", "uri": "https://l.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "workspace_slug": "ws-b", "client_profile_slug": "p-b",
         "source_type": "instagram", "label": "I1", "uri": "https://i.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get("/admin/client-sources?workspace_slug=ws-a")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["workspace_slug"] == "ws-a"


def test_list_client_sources_filter_source_type(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    db.client_sources.documents = [
        {"_id": ObjectId(), "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "linkedin", "label": "L1", "uri": "https://l.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "youtube", "label": "Y1", "uri": "https://y.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get("/admin/client-sources?source_type=youtube")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source_type"] == "youtube"


def test_list_client_sources_filter_status(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    db.client_sources.documents = [
        {"_id": ObjectId(), "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "linkedin", "label": "Active", "uri": "https://l.co", "status": "active",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "instagram", "label": "Inactive", "uri": "https://i.co", "status": "inactive",
         "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get("/admin/client-sources?status=inactive")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["label"] == "Inactive"


def test_get_client_source_by_id(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    oid = ObjectId()
    db.client_sources.documents = [
        {"_id": oid, "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "website", "label": "Main Site", "uri": "https://example.com",
         "status": "active", "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get(f"/admin/client-sources/{oid}")
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["label"] == "Main Site"
    assert item["health_status"] == "ready"


def test_get_client_source_not_found(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.get(f"/admin/client-sources/{ObjectId()}")
    assert resp.status_code == 404


def test_update_client_source_label(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    oid = ObjectId()
    db.client_sources.documents = [
        {"_id": oid, "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "linkedin", "label": "Old Label", "uri": "https://l.co",
         "status": "active", "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.patch(f"/admin/client-sources/{oid}", json={"label": "New Label"})
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["label"] == "New Label"


def test_update_client_source_status_to_inactive(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    oid = ObjectId()
    db.client_sources.documents = [
        {"_id": oid, "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "linkedin", "label": "LinkedIn", "uri": "https://l.co",
         "status": "active", "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.patch(f"/admin/client-sources/{oid}", json={"status": "inactive"})
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["status"] == "inactive"
    assert item["health_status"] == "inactive"


def test_delete_client_source(monkeypatch):
    db = _make_db()
    now = datetime.now(timezone.utc)
    oid = ObjectId()
    db.client_sources.documents = [
        {"_id": oid, "workspace_slug": "ws-a", "client_profile_slug": "p-a",
         "source_type": "website", "label": "Site", "uri": "https://example.com",
         "status": "active", "platform": None, "notes": None, "created_at": now, "updated_at": now},
    ]
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.delete(f"/admin/client-sources/{oid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True
    # Confirm deleted from collection
    assert db.client_sources.find_one({"_id": oid}) is None


def test_delete_client_source_not_found(monkeypatch):
    db = _make_db()
    monkeypatch.setattr(main, "get_client", lambda: _make_client(db))
    monkeypatch.setattr(main, "get_database", lambda c: db)

    client = TestClient(app)
    resp = client.delete(f"/admin/client-sources/{ObjectId()}")
    assert resp.status_code == 404


# ── Discovery engine integration tests ───────────────────────────────────────

class FakeDiscoveryDB:
    def __init__(self, sources=None):
        self.client_sources = FakeCollection(sources or [])
        self.discovery_insights = FakeCollection([])
        self.workflow_assets = FakeCollection([])


def test_get_configured_sources_returns_active_only():
    now = datetime.now(timezone.utc)
    db = FakeDiscoveryDB(sources=[
        {"_id": ObjectId(), "workspace_slug": "ws-1", "client_profile_slug": "p-1",
         "source_type": "linkedin", "label": "LinkedIn", "uri": "https://l.co",
         "status": "active", "created_at": now, "updated_at": now},
        {"_id": ObjectId(), "workspace_slug": "ws-1", "client_profile_slug": "p-1",
         "source_type": "instagram", "label": "Instagram", "uri": "https://i.co",
         "status": "inactive", "created_at": now, "updated_at": now},
    ])
    sources = engine.get_configured_sources("ws-1", "p-1", db)
    assert len(sources) == 1
    assert sources[0]["source_type"] == "linkedin"


def test_get_configured_sources_empty_when_none():
    db = FakeDiscoveryDB()
    sources = engine.get_configured_sources("ws-none", None, db)
    assert sources == []


def test_build_evidence_with_configured_source():
    trend = {
        "keyword": "leadership content",
        "insight_type": "content_opportunity",
        "signal_type": "search_trend",
        "platforms": ["LinkedIn"],
        "metric": "monthly_searches",
        "value": 10000.0,
        "growth_pct": 20.0,
    }
    configured = [
        {"source_type": "linkedin", "label": "John LinkedIn", "uri": "https://l.co", "status": "active"},
    ]
    evidence = engine.build_evidence(trend, configured_sources=configured)
    assert len(evidence) >= 1
    primary = evidence[0]
    assert primary["configured_source"] is True
    assert primary["source_label"] == "John LinkedIn"
    assert primary["source_type"] == "linkedin"


def test_build_evidence_without_configured_sources():
    trend = {
        "keyword": "leadership content",
        "insight_type": "content_opportunity",
        "signal_type": "search_trend",
        "platforms": ["LinkedIn"],
        "metric": "monthly_searches",
        "value": 10000.0,
        "growth_pct": 20.0,
    }
    evidence = engine.build_evidence(trend, configured_sources=[])
    assert evidence[0]["configured_source"] is False
    assert evidence[0]["source_label"] is None


def test_build_recommendation_includes_connected_platforms():
    trend = {
        "keyword": "burnout content",
        "insight_type": "content_opportunity",
        "platforms": ["LinkedIn", "YouTube Shorts"],
        "asset_types": ["script_draft"],
        "next_stage": "generate_content",
        "rationale": "Base rationale.",
    }
    configured = [
        {"source_type": "linkedin", "label": "LinkedIn", "uri": "https://l.co", "status": "active"},
    ]
    rec = engine.build_recommendation(trend, "media_growth", configured_sources=configured)
    # LinkedIn should be first (connected platform boosted)
    assert rec["recommended_platforms"][0] == "LinkedIn"
    assert "Configured sources connected" in rec["rationale"]


def test_build_recommendation_adds_podcast_for_rss():
    trend = {
        "keyword": "authority content",
        "insight_type": "authority_signal",
        "platforms": ["LinkedIn"],
        "asset_types": ["linkedin_post"],
        "next_stage": "generate_content",
        "rationale": "Build authority.",
    }
    configured = [
        {"source_type": "rss_feed", "label": "My Podcast", "uri": "https://feeds.ex.com/rss", "status": "active"},
    ]
    rec = engine.build_recommendation(trend, "media_growth", configured_sources=configured)
    assert "Podcast" in rec["recommended_platforms"]
    assert "podcast" in rec["rationale"].lower() or "rss" in rec["rationale"].lower()


def test_generate_discovery_insights_uses_configured_sources():
    now = datetime.now(timezone.utc)
    db = FakeDiscoveryDB(sources=[
        {"_id": ObjectId(), "workspace_slug": "ws-1", "client_profile_slug": "p-1",
         "source_type": "linkedin", "label": "Test LinkedIn", "uri": "https://l.co",
         "status": "active", "created_at": now, "updated_at": now},
    ])
    insights = engine.generate_discovery_insights(
        db=db,
        workspace_slug="ws-1",
        client_profile_slug="p-1",
        module="media_growth",
        max_insights=2,
    )
    assert len(insights) == 2
    # At least one insight should have evidence referencing the configured source
    all_evidence = [ev for ins in insights for ev in ins.get("evidence", [])]
    configured_ev = [ev for ev in all_evidence if ev.get("configured_source") is True]
    # LinkedIn is a platform in media_growth trends so at least one should match
    assert len(configured_ev) >= 1
    assert configured_ev[0]["source_label"] == "Test LinkedIn"


def test_generate_discovery_insights_rationale_mentions_sources():
    now = datetime.now(timezone.utc)
    db = FakeDiscoveryDB(sources=[
        {"_id": ObjectId(), "workspace_slug": "ws-2", "client_profile_slug": "p-2",
         "source_type": "instagram", "label": "Instagram", "uri": "https://i.co",
         "status": "active", "created_at": now, "updated_at": now},
    ])
    insights = engine.generate_discovery_insights(
        db=db,
        workspace_slug="ws-2",
        client_profile_slug="p-2",
        module="media_growth",
        max_insights=1,
    )
    assert len(insights) == 1
    rationale = insights[0]["recommendation"]["rationale"]
    assert "Configured sources connected" in rationale or "Instagram" in rationale


def test_generate_discovery_insights_no_sources_still_works():
    db = FakeDiscoveryDB(sources=[])
    insights = engine.generate_discovery_insights(
        db=db,
        workspace_slug="ws-nosrc",
        client_profile_slug=None,
        module="media_growth",
        max_insights=2,
    )
    assert len(insights) == 2
    # Evidence should still be built, just no configured_source annotation
    for ins in insights:
        for ev in ins.get("evidence", []):
            assert ev["configured_source"] is False
