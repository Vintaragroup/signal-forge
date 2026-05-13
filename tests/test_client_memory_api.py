"""Phase 6M: Tests for client memory, template recommendation, and memory update proposal endpoints."""
from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main

# ── Helpers ────────────────────────────────────────────────────────────────────

def _utc_now():
    return datetime.now(timezone.utc)


def _make_db(memories=None, proposals=None):
    """Build a mock db with client_memories and memory_update_proposals collections."""
    from bson import ObjectId

    db = MagicMock()

    _memories: list[dict] = []
    for m in (memories or []):
        entry = dict(m)
        if "_id" not in entry:
            entry["_id"] = ObjectId()
        _memories.append(entry)

    _proposals: list[dict] = []
    for p in (proposals or []):
        entry = dict(p)
        if "_id" not in entry:
            entry["_id"] = ObjectId()
        _proposals.append(entry)

    # ── client_memories ────────────────────────────────────────────────────────

    def mem_find_one(q, *args, **kwargs):
        for m in _memories:
            match = all(m.get(k) == v for k, v in q.items())
            if match:
                return dict(m)
        return None

    def mem_find(q=None, *args, **kwargs):
        q = q or {}
        results = [dict(m) for m in _memories if all(m.get(k) == v for k, v in q.items())]
        mock = MagicMock()
        mock.sort.return_value = mock
        mock.limit.return_value = iter(results)
        return mock

    def mem_insert_one(doc):
        doc["_id"] = ObjectId()
        _memories.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def mem_update_one(q, upd, *args, **kwargs):
        for m in _memories:
            match = all(m.get(k) == v for k, v in q.items())
            if match:
                if "$set" in upd:
                    m.update(upd["$set"])
                break

    db.client_memories.find_one = mem_find_one
    db.client_memories.find = mem_find
    db.client_memories.insert_one = mem_insert_one
    db.client_memories.update_one = mem_update_one

    # ── memory_update_proposals ────────────────────────────────────────────────

    def prop_find_one(q, *args, **kwargs):
        from bson import ObjectId as OID
        for p in _proposals:
            match = True
            for k, v in q.items():
                pv = p.get(k)
                if pv != v and str(pv) != str(v):
                    match = False
                    break
            if match:
                return dict(p)
        return None

    def prop_find(q=None, *args, **kwargs):
        q = q or {}
        results = []
        for p in _proposals:
            match = True
            for k, v in q.items():
                if v == "" or v is None:
                    continue
                if p.get(k) != v:
                    match = False
                    break
            if match:
                results.append(dict(p))
        mock = MagicMock()
        mock.sort.return_value = mock
        mock.limit.return_value = iter(results)
        return mock

    def prop_insert_one(doc):
        doc["_id"] = ObjectId()
        _proposals.append(doc)
        r = MagicMock()
        r.inserted_id = doc["_id"]
        return r

    def prop_update_one(q, upd, *args, **kwargs):
        from bson import ObjectId as OID
        for p in _proposals:
            match = True
            for k, v in q.items():
                pv = p.get(k)
                if pv != v and str(pv) != str(v):
                    match = False
                    break
            if match:
                if "$set" in upd:
                    p.update(upd["$set"])
                break

    db.memory_update_proposals.find_one = prop_find_one
    db.memory_update_proposals.find = prop_find
    db.memory_update_proposals.insert_one = prop_insert_one
    db.memory_update_proposals.update_one = prop_update_one

    return db


@pytest.fixture()
def client():
    return TestClient(main.app)


def _patch(db):
    """Context manager: patch get_client and get_database."""
    mongo_client = MagicMock()
    mongo_client.close = MagicMock()
    return patch.multiple(
        "main",
        get_client=lambda: mongo_client,
        get_database=lambda c: db,
    )


# ── Foundation Templates ────────────────────────────────────────────────────────

class TestFoundationTemplates:
    def test_list_returns_all_templates(self, client):
        resp = client.get("/foundation-templates")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        # At least the 8 templates we defined
        assert data["count"] >= 8
        slugs = [t["slug"] for t in data["items"]]
        assert "media_growth" in slugs
        assert "artist_growth" in slugs
        assert "sales_enablement" in slugs
        assert "recruiting" in slugs

    def test_get_template_by_slug(self, client):
        resp = client.get("/foundation-templates/media_growth")
        assert resp.status_code == 200
        data = resp.json()
        assert data["item"]["slug"] == "media_growth"
        assert data["item"]["name"] == "Media Growth"
        assert "description" in data["item"]
        assert "category" in data["item"]
        # keywords should NOT be exposed
        assert "keywords" not in data["item"]

    def test_get_unknown_template_404(self, client):
        resp = client.get("/foundation-templates/nonexistent_template")
        assert resp.status_code == 404

    def test_list_does_not_expose_keywords(self, client):
        resp = client.get("/foundation-templates")
        for t in resp.json()["items"]:
            assert "keywords" not in t


# ── Template Recommendation ─────────────────────────────────────────────────────

class TestTemplateRecommendation:
    def test_recommend_media_growth(self, client):
        resp = client.post("/template-recommendation", json={
            "client_name": "Podcast Pro",
            "industry": "podcasting",
            "description": "We run a media company producing podcast content for audiences",
            "primary_offer": "podcast sponsorships",
            "target_audience": "content creators and media operators",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "recommended_template" in data
        assert data["recommended_template"]["slug"] == "media_growth"
        assert "confidence_score" in data
        assert data["confidence_score"] > 0
        assert "reason" in data
        assert "alternate_templates" in data
        assert "assumptions" in data
        assert "missing_information" in data

    def test_recommend_insurance_growth(self, client):
        resp = client.post("/template-recommendation", json={
            "description": "Independent insurance broker focusing on referral networks",
            "industry": "insurance",
            "primary_offer": "insurance policies and coverage",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["recommended_template"]["slug"] == "insurance_growth"

    def test_recommend_requires_at_least_one_field(self, client):
        resp = client.post("/template-recommendation", json={
            "client_name": "",
            "description": "",
            "industry": "",
        })
        assert resp.status_code == 400

    def test_missing_information_flagged(self, client):
        resp = client.post("/template-recommendation", json={
            "description": "A generic business that does things",
        })
        assert resp.status_code == 200
        data = resp.json()
        # Should flag missing industry, primary_offer, target_audience
        assert "industry" in data["missing_information"]
        assert "primary_offer" in data["missing_information"]
        assert "target_audience" in data["missing_information"]

    def test_confidence_lower_for_sparse_profile(self, client):
        resp_sparse = client.post("/template-recommendation", json={
            "description": "company",
        })
        resp_rich = client.post("/template-recommendation", json={
            "description": "podcast media content creator youtube audience show newsletter publisher",
            "industry": "media",
            "primary_offer": "podcast sponsorships",
        })
        assert resp_sparse.json()["confidence_score"] <= resp_rich.json()["confidence_score"]

    def test_raw_scores_present(self, client):
        resp = client.post("/template-recommendation", json={
            "description": "sales team doing b2b prospecting",
            "industry": "b2b sales",
        })
        assert "raw_scores" in resp.json()
        assert len(resp.json()["raw_scores"]) == 8  # one per template

    def test_alternate_templates_excludes_top_pick(self, client):
        resp = client.post("/template-recommendation", json={
            "description": "podcast media content creator youtube audience",
            "industry": "media",
        })
        data = resp.json()
        top_slug = data["recommended_template"]["slug"]
        for alt in data["alternate_templates"]:
            assert alt["slug"] != top_slug


# ── Client Memory CRUD ──────────────────────────────────────────────────────────

class TestClientMemory:
    def test_create_memory_success(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/client-memory", json={
                "workspace_slug": "test-workspace",
                "foundation_template_slug": "media_growth",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert data["item"]["workspace_slug"] == "test-workspace"
        assert data["item"]["foundation_template_slug"] == "media_growth"
        assert data["item"]["version"] == 1
        # Memory body fields present
        assert "positioning" in data["item"]
        assert "icp" in data["item"]
        assert "voice_tone" in data["item"]
        assert "winning_patterns" in data["item"]
        assert "losing_patterns" in data["item"]

    def test_create_memory_sets_template_defaults(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/client-memory", json={
                "workspace_slug": "media-ws",
                "foundation_template_slug": "media_growth",
            })
        vt = resp.json()["item"]["voice_tone"]
        assert vt["tone"] == "engaging"
        assert vt["style"] == "authentic"

    def test_create_memory_idempotent(self, client):
        from bson import ObjectId
        existing = {
            "_id": ObjectId(),
            "workspace_slug": "existing-ws",
            "foundation_template_slug": "media_growth",
            "version": 2,
        }
        db = _make_db(memories=[existing])
        with _patch(db):
            resp = client.post("/client-memory", json={
                "workspace_slug": "existing-ws",
                "foundation_template_slug": "media_growth",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is False
        assert "already exists" in data["message"]

    def test_create_memory_invalid_template(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/client-memory", json={
                "workspace_slug": "ws",
                "foundation_template_slug": "fake_template",
            })
        assert resp.status_code == 400

    def test_create_memory_missing_workspace_slug(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/client-memory", json={
                "workspace_slug": "",
                "foundation_template_slug": "media_growth",
            })
        assert resp.status_code == 400

    def test_list_memories(self, client):
        from bson import ObjectId
        memories = [
            {"_id": ObjectId(), "workspace_slug": "ws1", "foundation_template_slug": "media_growth", "version": 1},
            {"_id": ObjectId(), "workspace_slug": "ws2", "foundation_template_slug": "recruiting", "version": 1},
        ]
        db = _make_db(memories=memories)
        with _patch(db):
            resp = client.get("/client-memory?workspace_slug=ws1")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["workspace_slug"] == "ws1"

    def test_update_memory(self, client):
        from bson import ObjectId
        mem_id = ObjectId()
        memories = [{
            "_id": mem_id,
            "workspace_slug": "ws1",
            "foundation_template_slug": "media_growth",
            "version": 1,
            "winning_patterns": [],
            "losing_patterns": [],
            "approved_claims": [],
        }]
        db = _make_db(memories=memories)
        with _patch(db):
            resp = client.patch(f"/client-memory/{mem_id}", json={
                "winning_patterns": ["Short video outperforms long-form"],
                "approved_claims": ["Top-rated podcast in category"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["item"]["version"] == 2
        assert "Short video outperforms long-form" in data["item"]["winning_patterns"]
        assert "Top-rated podcast in category" in data["item"]["approved_claims"]

    def test_update_memory_invalid_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.patch("/client-memory/not-an-object-id", json={"winning_patterns": []})
        assert resp.status_code == 400

    def test_update_memory_not_found(self, client):
        from bson import ObjectId
        db = _make_db()
        with _patch(db):
            resp = client.patch(f"/client-memory/{ObjectId()}", json={"winning_patterns": []})
        assert resp.status_code == 404

    def test_memory_brief_generation(self, client):
        from bson import ObjectId
        mem_id = ObjectId()
        memories = [{
            "_id": mem_id,
            "workspace_slug": "brief-ws",
            "foundation_template_slug": "media_growth",
            "foundation_template_name": "Media Growth",
            "version": 3,
            "positioning": {
                "what_they_do": "Produce podcast content",
                "who_they_help": "Media operators",
                "why_buyers_choose": "Best quality",
                "proof_points": ["500k downloads"],
                "differentiators": ["Unique format"],
            },
            "icp": {"company_type": "Media", "buyer": "CMO", "size": "50-200", "geography": "US"},
            "approved_claims": ["Top-rated"],
            "blocked_claims": ["Guaranteed results"],
            "winning_patterns": ["Short-form wins"],
            "losing_patterns": ["Overly promotional"],
            "approval_tendencies": {"approval_rate": 0.85, "avg_revision_count": 1.2, "common_rejection_reasons": []},
            "performance_notes": ["Q1 best quarter"],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }]
        db = _make_db(memories=memories)
        with _patch(db):
            resp = client.get(f"/client-memory/{mem_id}/brief")
        assert resp.status_code == 200
        data = resp.json()
        assert "brief_markdown" in data
        brief = data["brief_markdown"]
        assert "brief-ws" in brief
        assert "Media Growth" in brief
        assert "Produce podcast content" in brief
        assert "Top-rated" in brief
        assert "Guaranteed results" in brief
        assert "85%" in brief  # approval rate

    def test_memory_brief_invalid_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.get("/client-memory/not-an-id/brief")
        assert resp.status_code == 400


# ── Memory Update Proposals ─────────────────────────────────────────────────────

class TestMemoryUpdateProposals:
    def test_create_proposal(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "ws1",
                "proposed_change": {
                    "field": "winning_patterns",
                    "change_type": "add",
                    "new_value": "LinkedIn posts outperform Twitter",
                },
                "evidence": "5 LinkedIn posts approved vs 1 Twitter",
                "confidence": 0.75,
                "source": "manual",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["item"]["status"] == "pending"
        assert data["item"]["confidence"] == 0.75
        assert data["item"]["workspace_slug"] == "ws1"

    def test_create_proposal_invalid_field(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "ws1",
                "proposed_change": {
                    "field": "nonexistent_field",
                    "change_type": "add",
                    "new_value": "test",
                },
                "confidence": 0.5,
            })
        assert resp.status_code == 400

    def test_create_proposal_missing_workspace(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.post("/memory-update-proposals", json={
                "workspace_slug": "",
                "proposed_change": {"field": "winning_patterns", "new_value": "test"},
            })
        assert resp.status_code == 400

    def test_list_proposals(self, client):
        from bson import ObjectId
        proposals = [
            {"_id": ObjectId(), "workspace_slug": "ws1", "status": "pending", "source": "auto"},
            {"_id": ObjectId(), "workspace_slug": "ws1", "status": "approved", "source": "auto"},
        ]
        db = _make_db(proposals=proposals)
        with _patch(db):
            resp = client.get("/memory-update-proposals?workspace_slug=ws1")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_list_proposals_filter_by_status(self, client):
        from bson import ObjectId
        proposals = [
            {"_id": ObjectId(), "workspace_slug": "ws1", "status": "pending"},
            {"_id": ObjectId(), "workspace_slug": "ws1", "status": "approved"},
        ]
        db = _make_db(proposals=proposals)
        with _patch(db):
            resp = client.get("/memory-update-proposals?workspace_slug=ws1&status=pending")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
        assert resp.json()["items"][0]["status"] == "pending"

    def test_approve_proposal_applies_add_to_list(self, client):
        from bson import ObjectId
        mem_id = ObjectId()
        prop_id = ObjectId()
        memories = [{
            "_id": mem_id,
            "workspace_slug": "ws1",
            "winning_patterns": ["existing pattern"],
            "version": 1,
        }]
        proposals = [{
            "_id": prop_id,
            "workspace_slug": "ws1",
            "client_memory_id": str(mem_id),
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "new winning pattern",
            },
        }]
        db = _make_db(memories=memories, proposals=proposals)
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={
                "status": "approved",
                "reviewed_by": "operator",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["item"]["status"] == "approved"
        assert data["applied_to_memory"] is True
        # Verify memory was updated
        updated_mem = db.client_memories.find_one({"_id": mem_id})
        assert "new winning pattern" in updated_mem["winning_patterns"]
        assert "existing pattern" in updated_mem["winning_patterns"]

    def test_approve_proposal_update_replaces_value(self, client):
        from bson import ObjectId
        mem_id = ObjectId()
        prop_id = ObjectId()
        memories = [{
            "_id": mem_id,
            "workspace_slug": "ws1",
            "distribution_preferences": {"channels": ["LinkedIn"], "manual_only": True},
            "version": 1,
        }]
        proposals = [{
            "_id": prop_id,
            "workspace_slug": "ws1",
            "client_memory_id": str(mem_id),
            "status": "pending",
            "proposed_change": {
                "field": "distribution_preferences",
                "change_type": "update",
                "new_value": {"channels": ["LinkedIn", "Email"], "manual_only": True},
            },
        }]
        db = _make_db(memories=memories, proposals=proposals)
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "approved"})
        assert resp.status_code == 200
        updated_mem = db.client_memories.find_one({"_id": mem_id})
        assert "Email" in updated_mem["distribution_preferences"]["channels"]

    def test_reject_proposal_does_not_modify_memory(self, client):
        from bson import ObjectId
        mem_id = ObjectId()
        prop_id = ObjectId()
        memories = [{
            "_id": mem_id,
            "workspace_slug": "ws1",
            "winning_patterns": ["existing"],
            "version": 1,
        }]
        proposals = [{
            "_id": prop_id,
            "workspace_slug": "ws1",
            "client_memory_id": str(mem_id),
            "status": "pending",
            "proposed_change": {
                "field": "winning_patterns",
                "change_type": "add",
                "new_value": "should not be added",
            },
        }]
        db = _make_db(memories=memories, proposals=proposals)
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "rejected"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["applied_to_memory"] is False
        updated_mem = db.client_memories.find_one({"_id": mem_id})
        assert "should not be added" not in (updated_mem.get("winning_patterns") or [])

    def test_decide_already_decided_proposal_400(self, client):
        from bson import ObjectId
        prop_id = ObjectId()
        proposals = [{
            "_id": prop_id,
            "workspace_slug": "ws1",
            "status": "approved",
            "proposed_change": {},
        }]
        db = _make_db(proposals=proposals)
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{prop_id}", json={"status": "rejected"})
        assert resp.status_code == 400

    def test_decide_invalid_proposal_id(self, client):
        db = _make_db()
        with _patch(db):
            resp = client.patch("/memory-update-proposals/not-an-id", json={"status": "approved"})
        assert resp.status_code == 400

    def test_decide_nonexistent_proposal(self, client):
        from bson import ObjectId
        db = _make_db()
        with _patch(db):
            resp = client.patch(f"/memory-update-proposals/{ObjectId()}", json={"status": "approved"})
        assert resp.status_code == 404


# ── Scoring helper unit tests ────────────────────────────────────────────────────

class TestScoringHelpers:
    def test_score_exact_match(self):
        template = {"keywords": ["podcast", "media", "creator"]}
        score = main._score_template_against_profile(template, "we run a podcast and media company for creators")
        assert score > 0.9

    def test_score_no_match(self):
        template = {"keywords": ["podcast", "media", "creator"]}
        score = main._score_template_against_profile(template, "insurance broker selling life policies")
        assert score == 0.0

    def test_score_partial_match(self):
        template = {"keywords": ["podcast", "media", "creator", "audience", "show"]}
        score = main._score_template_against_profile(template, "we make a podcast show")
        assert 0.0 < score < 1.0

    def test_score_empty_keywords(self):
        template = {"keywords": []}
        score = main._score_template_against_profile(template, "anything")
        assert score == 0.0

    def test_build_profile_text_concatenates_all_strings(self):
        text = main._build_profile_text({
            "client_name": "Acme",
            "industry": "media",
            "goals": "grow audience",
            "ignored_list": ["a", "b"],
        })
        assert "Acme" in text
        assert "media" in text
        assert "grow audience" in text
        assert "a" in text

    def test_make_memory_skeleton_has_all_fields(self):
        skeleton = main._make_memory_skeleton("media_growth")
        required_fields = [
            "positioning", "icp", "voice_tone", "offers",
            "approved_claims", "blocked_claims", "winning_patterns",
            "losing_patterns", "source_preferences", "workflow_preferences",
            "distribution_preferences", "approval_tendencies", "performance_notes",
        ]
        for f in required_fields:
            assert f in skeleton, f"Missing field: {f}"

    def test_make_memory_skeleton_unknown_template(self):
        # Should not crash, just return defaults
        skeleton = main._make_memory_skeleton("unknown_template")
        assert "positioning" in skeleton
        assert "voice_tone" in skeleton
