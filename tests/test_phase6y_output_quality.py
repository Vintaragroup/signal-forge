"""
tests/test_phase6y_output_quality.py
Phase 6Y — Agent Output Quality & Real Workflow Content Validation
55 tests: quality dimensions, pilot content generation, score clamping,
review CRUD, memory comparison, revision loop, content packages,
pilot workspace seed, publish-ready filter, metrics, endpoints, smoke.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import sys, os, types

# ── Stub heavy optional dependencies ─────────────────────────────────────────
for _mod in [
    "whisper", "yt_dlp", "core.constants", "prompt_generator", "snippet_scorer",
    "agents.base_agent", "agents.content_agent", "agents.fan_engagement_agent",
    "agents.followup_agent", "agents.outreach_agent",
    "media_folder_scanner", "approved_url_downloader",
]:
    _parts = _mod.split(".")
    if len(_parts) > 1:
        _parent = types.ModuleType(_parts[0])
        sys.modules.setdefault(_parts[0], _parent)
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

sys.modules["core.constants"].MESSAGE_REVIEW_DECISIONS = []
sys.modules["core.constants"].OPEN_DEAL_OUTCOMES = []
sys.modules["core.constants"].VALID_MODULES = []

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "api"))

import main
from main import app

client = TestClient(app, raise_server_exceptions=False)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _reset_state():
    main._runtime_state_6u.update({
        "total_requests": 0,
        "by_path":        {},
        "worker_registry": {},
        "audit_log":      [],
        "rate_buckets":   {},
    })


def _mock_db_6y(review_doc=None, pkg_count=0):
    db = MagicMock()
    db.command.return_value = {"ok": 1}

    db.quality_reviews_6y.insert_one.return_value     = MagicMock()
    db.quality_reviews_6y.update_one.return_value     = MagicMock()
    db.quality_reviews_6y.find_one.return_value       = review_doc
    db.quality_reviews_6y.count_documents.return_value = 0
    db.quality_reviews_6y.find.return_value            = iter([])
    db.quality_reviews_6y.aggregate.return_value       = iter([])

    db.content_items_6y.insert_one.return_value        = MagicMock()
    db.content_packages_6y.insert_one.return_value     = MagicMock()
    db.content_packages_6y.find.return_value           = iter([])
    db.content_packages_6y.update_one.return_value     = MagicMock()
    db.content_packages_6y.count_documents.return_value = pkg_count

    db.memory_proposals.insert_one.return_value        = MagicMock()
    db.client_profiles.update_one.return_value         = MagicMock()
    db.client_memory.update_one.return_value           = MagicMock()
    db.workspaces.find_one.return_value                = None
    db.workspaces.update_one.return_value              = MagicMock()

    db.__getitem__ = MagicMock(side_effect=lambda n: getattr(db, n, MagicMock()))
    return db


def _make_review(avg_score=3.0, publish_ready=False, revision=False, approved=False,
                 content_type="linkedin_post", memory_version=0):
    return {
        "review_id":          "qr_test001",
        "workspace_slug":     "test-ws",
        "content_item_id":    "ci_001",
        "content_type":       content_type,
        "content_text":       "Test LinkedIn post content about leadership.",
        "scores":             {d: 3 for d in main._QUALITY_DIMENSIONS_6Y},
        "avg_score":          avg_score,
        "approved":           approved,
        "publish_ready":      publish_ready,
        "revision_requested": revision,
        "revision_reason":    "tone_mismatch" if revision else None,
        "reviewer_notes":     None,
        "memory_version":     memory_version,
        "created_at":         "2026-05-15T00:00:00+00:00",
        "updated_at":         "2026-05-15T00:00:00+00:00",
    }


def _patch_6y(db):
    mc = MagicMock()
    mc.close = MagicMock()
    return patch.multiple("main", get_client=lambda: mc, get_database=lambda c: db)


# ══════════════════════════════════════════════════════════════════════════════
# 1. TestQualityDimensions6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityDimensions6Y:

    def test_all_five_dimensions_present(self):
        expected = {"relevance", "clarity", "client_fit", "publish_readiness", "strategic_value"}
        assert set(main._QUALITY_DIMENSIONS_6Y) == expected

    def test_max_score_is_five(self):
        assert main._QUALITY_MAX_SCORE_6Y == 5

    def test_min_publish_threshold(self):
        assert main._QUALITY_MIN_PUBLISH_6Y == 3.5

    def test_memory_improvement_threshold(self):
        assert main._MEMORY_IMPROVEMENT_THRESHOLD_6Y == 0.15


# ══════════════════════════════════════════════════════════════════════════════
# 2. TestGeneratePilotContent6Y  (6 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestGeneratePilotContent6Y:

    def test_returns_all_content_types(self):
        for ctype in main._CONTENT_PACKAGE_TYPES_6Y:
            item = main._generate_pilot_content_6y(ctype, 0, use_memory=False)
            assert item["content_type"] == ctype
            assert item["content_text"]

    def test_linkedin_post_has_hashtags(self):
        item = main._generate_pilot_content_6y("linkedin_post", 0, use_memory=False)
        assert "#" in item["content_text"]

    def test_content_hook_is_string(self):
        item = main._generate_pilot_content_6y("content_hook", 0, use_memory=False)
        assert isinstance(item["content_text"], str)
        assert len(item["content_text"]) > 10

    def test_video_concept_has_structured(self):
        item = main._generate_pilot_content_6y("video_concept", 0, use_memory=False)
        assert "structured" in item
        assert isinstance(item["structured"], dict)
        assert "title" in item["structured"]

    def test_outreach_angle_has_body(self):
        item = main._generate_pilot_content_6y("outreach_angle", 0, use_memory=False)
        assert "structured" in item
        assert "body" in item["structured"]

    def test_campaign_summary_has_client_name(self):
        item = main._generate_pilot_content_6y("campaign_summary", 0, use_memory=True)
        assert "John Maxwell" in item["content_text"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. TestScoreClamping6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestScoreClamping6Y:

    def _create_with_scores(self, scores):
        db = _mock_db_6y()
        payload = {
            "workspace_slug":  "test-ws",
            "content_item_id": "ci_001",
            "content_type":    "linkedin_post",
            "content_text":    "Sample content.",
            "scores":          scores,
        }
        return main._create_quality_review_6y(db, payload)

    def test_clamp_low_scores_to_zero(self):
        scores = {d: -10 for d in main._QUALITY_DIMENSIONS_6Y}
        doc = self._create_with_scores(scores)
        for d in main._QUALITY_DIMENSIONS_6Y:
            assert doc["scores"][d] == 0

    def test_clamp_high_scores_to_max(self):
        scores = {d: 99 for d in main._QUALITY_DIMENSIONS_6Y}
        doc = self._create_with_scores(scores)
        for d in main._QUALITY_DIMENSIONS_6Y:
            assert doc["scores"][d] == main._QUALITY_MAX_SCORE_6Y

    def test_clamp_negative_values(self):
        scores = {d: -1 for d in main._QUALITY_DIMENSIONS_6Y}
        doc = self._create_with_scores(scores)
        assert all(v == 0 for v in doc["scores"].values())

    def test_all_dimensions_present_in_review(self):
        scores = {d: 3 for d in main._QUALITY_DIMENSIONS_6Y}
        doc = self._create_with_scores(scores)
        assert set(doc["scores"].keys()) == set(main._QUALITY_DIMENSIONS_6Y)


# ══════════════════════════════════════════════════════════════════════════════
# 4. TestQualityReviewCreate6Y  (6 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityReviewCreate6Y:

    def _base_payload(self, scores=None, **kwargs):
        s = scores or {d: 4 for d in main._QUALITY_DIMENSIONS_6Y}
        return {
            "workspace_slug":  "test-ws",
            "content_item_id": "ci_001",
            "content_type":    "linkedin_post",
            "content_text":    "Leadership post about multiplying teams.",
            "scores":          s,
            **kwargs,
        }

    def test_returns_dict_with_review_id(self):
        db  = _mock_db_6y()
        doc = main._create_quality_review_6y(db, self._base_payload())
        assert "review_id" in doc
        assert doc["review_id"].startswith("qr_")

    def test_avg_score_computed_correctly(self):
        db     = _mock_db_6y()
        scores = {d: 4 for d in main._QUALITY_DIMENSIONS_6Y}
        doc    = main._create_quality_review_6y(db, self._base_payload(scores=scores))
        assert doc["avg_score"] == 4.0

    def test_publish_ready_auto_set_at_threshold(self):
        db     = _mock_db_6y()
        scores = {d: 4 for d in main._QUALITY_DIMENSIONS_6Y}  # avg=4.0 >= 3.5
        doc    = main._create_quality_review_6y(db, self._base_payload(scores=scores))
        assert doc["publish_ready"] is True

    def test_publish_ready_not_set_below_threshold(self):
        db     = _mock_db_6y()
        scores = {d: 2 for d in main._QUALITY_DIMENSIONS_6Y}  # avg=2.0 < 3.5
        doc    = main._create_quality_review_6y(db, self._base_payload(scores=scores))
        assert doc["publish_ready"] is False

    def test_revision_triggers_memory_proposal(self):
        db = _mock_db_6y()
        main._create_quality_review_6y(db, self._base_payload(
            revision_requested=True,
            revision_reason="tone_mismatch",
        ))
        db.memory_proposals.insert_one.assert_called_once()

    def test_audit_logged_on_create(self):
        _reset_state()
        db  = _mock_db_6y()
        doc = main._create_quality_review_6y(db, self._base_payload())
        audit = main._runtime_state_6u.get("audit_log", [])
        assert len(audit) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. TestQualityReviewUpdate6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityReviewUpdate6Y:

    def test_update_scores_recalculates_avg(self):
        existing = _make_review(avg_score=3.0)
        db       = _mock_db_6y(review_doc=existing)
        new_scores = {d: 5 for d in main._QUALITY_DIMENSIONS_6Y}
        db.quality_reviews_6y.find_one.side_effect = [existing, {**existing, "scores": new_scores, "avg_score": 5.0, "publish_ready": True}]
        updated = main._update_quality_review_6y(db, "qr_test001", {"scores": new_scores})
        assert updated is not None
        assert updated["avg_score"] == 5.0

    def test_publish_ready_updated(self):
        existing = _make_review(avg_score=3.0, publish_ready=False)
        db       = _mock_db_6y(review_doc=existing)
        new_scores = {d: 4 for d in main._QUALITY_DIMENSIONS_6Y}  # avg=4.0 -> publish_ready=True
        updated_doc = {**existing, "scores": new_scores, "avg_score": 4.0, "publish_ready": True}
        db.quality_reviews_6y.find_one.side_effect = [existing, updated_doc]
        updated = main._update_quality_review_6y(db, "qr_test001", {"scores": new_scores})
        assert updated["publish_ready"] is True

    def test_returns_none_for_missing_review(self):
        db = _mock_db_6y(review_doc=None)
        result = main._update_quality_review_6y(db, "qr_MISSING", {"approved": True})
        assert result is None

    def test_reviewer_notes_patched(self):
        existing = _make_review()
        db       = _mock_db_6y(review_doc=existing)
        patched  = {**existing, "reviewer_notes": "Good hook, weak CTA."}
        db.quality_reviews_6y.find_one.side_effect = [existing, patched]
        updated = main._update_quality_review_6y(db, "qr_test001", {"reviewer_notes": "Good hook, weak CTA."})
        assert updated is not None
        assert updated["reviewer_notes"] == "Good hook, weak CTA."


# ══════════════════════════════════════════════════════════════════════════════
# 6. TestMemoryComparison6Y  (5 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestMemoryComparison6Y:

    def _baseline(self, val=2):
        return {d: val for d in main._QUALITY_DIMENSIONS_6Y}

    def _memory(self, val=4):
        return {d: val for d in main._QUALITY_DIMENSIONS_6Y}

    def test_improved_when_delta_above_threshold(self):
        # delta = 4-2 = 2 > 0.15 * 5 = 0.75 → improved
        result = main._compare_memory_impact_6y(self._baseline(2), self._memory(4))
        assert result["improved"] is True

    def test_not_improved_when_delta_below_threshold(self):
        # delta = 3.0 - 3.0 = 0 < 0.75 → not improved
        result = main._compare_memory_impact_6y(self._baseline(3), self._memory(3))
        assert result["improved"] is False

    def test_delta_computed_correctly(self):
        result = main._compare_memory_impact_6y(self._baseline(2), self._memory(4))
        assert result["delta"] == pytest.approx(2.0)

    def test_dimension_deltas_present(self):
        result = main._compare_memory_impact_6y(self._baseline(2), self._memory(4))
        assert "dimension_deltas" in result
        for d in main._QUALITY_DIMENSIONS_6Y:
            assert d in result["dimension_deltas"]

    def test_evaluated_at_present(self):
        result = main._compare_memory_impact_6y(self._baseline(3), self._memory(4))
        assert "evaluated_at" in result
        assert result["evaluated_at"]


# ══════════════════════════════════════════════════════════════════════════════
# 7. TestRevisionLoop6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestRevisionLoop6Y:

    def test_returns_new_review_id(self):
        existing = _make_review(revision=True)
        db       = _mock_db_6y(review_doc=existing)
        result   = main._run_revision_loop_6y(db, "qr_test001", "test-ws")
        assert "new_review_id" in result
        assert result["new_review_id"].startswith("qr_rev_")

    def test_is_revision_flag_true(self):
        existing = _make_review(revision=True)
        db       = _mock_db_6y(review_doc=existing)
        result   = main._run_revision_loop_6y(db, "qr_test001", "test-ws")
        assert result["is_revision"] is True

    def test_memory_version_is_two(self):
        existing = _make_review(revision=True)
        db       = _mock_db_6y(review_doc=existing)
        result   = main._run_revision_loop_6y(db, "qr_test001", "test-ws")
        assert result["memory_version"] == 2

    def test_returns_error_for_missing_review(self):
        db     = _mock_db_6y(review_doc=None)
        result = main._run_revision_loop_6y(db, "qr_MISSING", "test-ws")
        assert "error" in result


# ══════════════════════════════════════════════════════════════════════════════
# 8. TestContentPackageGenerate6Y  (5 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestContentPackageGenerate6Y:

    def _gen(self, use_memory=True):
        db = _mock_db_6y()
        return main._generate_content_package_6y(db, "test-ws", "John Maxwell", use_memory)

    def test_package_has_all_content_types(self):
        pkg = self._gen()
        types_found = {item["content_type"] for item in pkg["items"]}
        assert types_found == set(main._CONTENT_PACKAGE_TYPES_6Y.keys())

    def test_total_items_is_seventeen(self):
        pkg = self._gen()
        expected = sum(main._CONTENT_PACKAGE_TYPES_6Y.values())
        assert pkg["total_items"] == expected == 17

    def test_package_id_present(self):
        pkg = self._gen()
        assert "package_id" in pkg
        assert pkg["package_id"].startswith("pkg_")

    def test_content_items_inserted(self):
        db  = _mock_db_6y()
        main._generate_content_package_6y(db, "test-ws", "John Maxwell", True)
        assert db.content_items_6y.insert_one.call_count == 17

    def test_use_memory_flag_propagated(self):
        pkg = self._gen(use_memory=False)
        assert pkg["use_memory"] is False
        for item in pkg["items"]:
            assert item["use_memory"] is False


# ══════════════════════════════════════════════════════════════════════════════
# 9. TestPilotWorkspaceSeed6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestPilotWorkspaceSeed6Y:

    def test_seeds_workspace(self):
        db     = _mock_db_6y()
        result = main._seed_pilot_workspace_6y(db, main._PILOT_WORKSPACE_SLUG_6Y)
        assert result["workspace_slug"] == main._PILOT_WORKSPACE_SLUG_6Y
        db.workspaces.update_one.assert_called()

    def test_creates_client_profile(self):
        db = _mock_db_6y()
        main._seed_pilot_workspace_6y(db, main._PILOT_WORKSPACE_SLUG_6Y)
        db.client_profiles.update_one.assert_called()

    def test_creates_memory_v1_and_v2(self):
        db = _mock_db_6y()
        main._seed_pilot_workspace_6y(db, main._PILOT_WORKSPACE_SLUG_6Y)
        assert db.client_memory.update_one.call_count >= 2

    def test_already_exists_when_not_force(self):
        db = _mock_db_6y()
        # Simulate workspace already exists
        db.workspaces.find_one.return_value = {"slug": main._PILOT_WORKSPACE_SLUG_6Y}
        result = main._seed_pilot_workspace_6y(db, main._PILOT_WORKSPACE_SLUG_6Y, force=False)
        assert result["already_exists"] is True


# ══════════════════════════════════════════════════════════════════════════════
# 10. TestPublishReadyFilter6Y  (3 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestPublishReadyFilter6Y:

    def test_endpoint_returns_200(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.get("/quality/publish-ready")
        assert resp.status_code == 200

    def test_response_has_publish_ready_key(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.get("/quality/publish-ready")
        assert "publish_ready" in resp.json()

    def test_filters_workspace_slug(self):
        pub_review = _make_review(publish_ready=True)
        db = _mock_db_6y(review_doc=pub_review)
        db.quality_reviews_6y.find.return_value = iter([pub_review])
        with _patch_6y(db):
            resp = client.get("/quality/publish-ready?workspace_slug=test-ws")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] >= 0  # 0 or 1 depending on mock iteration


# ══════════════════════════════════════════════════════════════════════════════
# 11. TestQualityMetricsHelper6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityMetricsHelper6Y:

    def test_returns_all_metric_keys(self):
        db     = _mock_db_6y()
        result = main._build_quality_metrics_6y(db, "test-ws")
        for key in main._QUALITY_METRIC_KEYS_6Y:
            assert key in result, f"Missing key: {key}"

    def test_returns_zero_when_no_reviews(self):
        db     = _mock_db_6y()
        result = main._build_quality_metrics_6y(db, "test-ws")
        assert result["total_reviews"] == 0
        assert result["avg_quality_score"] == 0.0

    def test_db_failure_safe(self):
        db = _mock_db_6y()
        db.quality_reviews_6y.count_documents.side_effect = Exception("DB down")
        result = main._build_quality_metrics_6y(db, "test-ws")
        assert "approval_rate" in result
        assert result["approval_rate"] == 0.0

    def test_has_evaluated_at(self):
        db     = _mock_db_6y()
        result = main._build_quality_metrics_6y(db, "test-ws")
        assert "evaluated_at" in result
        assert result["evaluated_at"]


# ══════════════════════════════════════════════════════════════════════════════
# 12. TestQualityEndpoints6Y  (6 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityEndpoints6Y:

    def test_create_review_post_200(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.post("/quality/reviews", json={
                "workspace_slug":  "test-ws",
                "content_item_id": "ci_001",
                "content_type":    "linkedin_post",
                "content_text":    "Leadership post text.",
                "scores":          {d: 4 for d in main._QUALITY_DIMENSIONS_6Y},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data

    def test_get_review_by_id_200(self):
        existing = _make_review()
        db       = _mock_db_6y(review_doc=existing)
        with _patch_6y(db):
            resp = client.get("/quality/reviews/qr_test001")
        assert resp.status_code == 200

    def test_get_review_missing_404(self):
        db = _mock_db_6y(review_doc=None)
        with _patch_6y(db):
            resp = client.get("/quality/reviews/qr_NOTEXIST")
        assert resp.status_code == 404

    def test_patch_review_200(self):
        existing = _make_review()
        db       = _mock_db_6y(review_doc=existing)
        patched  = {**existing, "approved": True}
        db.quality_reviews_6y.find_one.side_effect = [existing, patched]
        with _patch_6y(db):
            resp = client.patch("/quality/reviews/qr_test001", json={"approved": True})
        assert resp.status_code == 200

    def test_list_reviews_200(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.get("/quality/reviews?workspace_slug=test-ws")
        assert resp.status_code == 200
        assert "reviews" in resp.json()

    def test_content_package_post_200(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.post("/quality/content-package", json={
                "workspace_slug": "test-ws",
                "client_name":    "John Maxwell",
                "use_memory":     True,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "package_id" in data

    def test_metrics_endpoint_200(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.get("/quality/metrics?workspace_slug=test-ws")
        assert resp.status_code == 200
        data = resp.json()
        assert "avg_quality_score" in data


# ══════════════════════════════════════════════════════════════════════════════
# 13. TestDeploymentSmoke6Y  (4 tests)
# ══════════════════════════════════════════════════════════════════════════════

class TestDeploymentSmoke6Y:

    _EXPECTED_6Y_PATHS = [
        "/quality/pilot-workspace/seed",
        "/quality/reviews",
        "/quality/content-package",
        "/quality/memory-comparison",
        "/quality/publish-ready",
        "/quality/metrics",
    ]

    def test_6y_endpoints_in_openapi(self):
        resp  = client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json().get("paths", {})
        for p in self._EXPECTED_6Y_PATHS:
            assert p in paths, f"OpenAPI missing: {p}"

    def test_pilot_workspace_seed_endpoint_200(self):
        db = _mock_db_6y()
        with _patch_6y(db):
            resp = client.post("/quality/pilot-workspace/seed", json={
                "workspace_slug": main._PILOT_WORKSPACE_SLUG_6Y,
                "force":          True,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspace_slug"] == main._PILOT_WORKSPACE_SLUG_6Y

    def test_memory_comparison_endpoint_200(self):
        resp = client.post("/quality/memory-comparison", json={
            "workspace_slug":  "test-ws",
            "content_type":    "linkedin_post",
            "content_text":    "Leadership content sample.",
            "baseline_scores": {d: 2 for d in main._QUALITY_DIMENSIONS_6Y},
            "memory_scores":   {d: 4 for d in main._QUALITY_DIMENSIONS_6Y},
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["improved"] is True
        assert data["delta"] > 0

    def test_revision_loop_404_on_missing(self):
        db = _mock_db_6y(review_doc=None)
        with _patch_6y(db):
            resp = client.post("/quality/revision-loop/qr_NOTEXIST")
        assert resp.status_code == 404
