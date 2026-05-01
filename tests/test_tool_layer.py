from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app
from tools.base_tool import BaseTool
from tools.browser_scroll_tool import BrowserScrollTool
from tools.contact_extraction_tool import extract_contact_fields
from tools.manual_import_tool import ManualCandidateImportTool
from tools.source_validator_tool import classify_source, score_source
from tools.web_search_tool import WebSearchTool
from tools.website_scraper_tool import WebsiteScraperTool


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, sort_spec):
        if isinstance(sort_spec, str):
            key = sort_spec
            reverse = False
        else:
            key, direction = sort_spec[0]
            reverse = direction < 0
        self.documents.sort(key=lambda item: item.get(key) or 0, reverse=reverse)
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
        return FakeCursor([document for document in self.documents if self.matches(document, query)])

    def find_one(self, query, sort=None):
        documents = list(self.find(query))
        if sort:
            documents = list(FakeCursor(documents).sort(sort))
        return documents[0] if documents else None

    def insert_one(self, document):
        if "_id" not in document:
            document["_id"] = ObjectId()
        self.documents.append(document)
        return InsertResult(document["_id"])

    def update_one(self, query, update, upsert=False):
        document = self.find_one(query)
        if not document:
            return None
        for key, value in (update.get("$set") or {}).items():
            document[key] = value
        for key, value in (update.get("$push") or {}).items():
            document.setdefault(key, []).append(value)
        return None

    def matches(self, document, query):
        for key, value in query.items():
            if key == "$or":
                if not any(self.matches(document, condition) for condition in value):
                    return False
                continue
            if document.get(key) != value:
                return False
        return True


class FakeDatabase:
    def __init__(self):
        self.tool_runs = FakeCollection([])
        self.scraped_candidates = FakeCollection([])
        self.approval_requests = FakeCollection([])
        self.agent_artifacts = FakeCollection([])
        self.contacts = FakeCollection([])
        self.leads = FakeCollection([])


class FakeClient:
    def close(self):
        return None


def patch_database(monkeypatch, db):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    monkeypatch.setattr(main, "get_database", lambda _client: db)


def test_mock_search_creates_review_candidates():
    db = FakeDatabase()
    result = WebSearchTool().run("roofing contractor", "contractor_growth", "Austin, TX", 2, db=db)

    assert result["simulation_only"] is True
    assert len(result["candidate_ids"]) == 2
    assert len(db.tool_runs.documents) == 1
    assert len(db.approval_requests.documents) == 2
    assert len(db.agent_artifacts.documents) == 1
    assert db.tool_runs.documents[0]["mode"] == "mock_read_only"
    assert all(candidate["status"] == "needs_review" for candidate in db.scraped_candidates.documents)
    assert all(candidate["outbound_actions_taken"] == 0 for candidate in db.scraped_candidates.documents)


def test_website_scraper_parses_public_html_sample():
    html = """
    <html>
      <head><title>Apex Roofing - Austin</title><meta name="description" content="Roofing repairs in Austin"></head>
      <body><h1>Apex Roofing</h1><p>Call 512-555-0142 or email hello@example.com in Austin, TX.</p></body>
    </html>
    """
    result = WebsiteScraperTool().parse_html(html, "https://apex-roofing.example.com")

    assert result["title"] == "Apex Roofing - Austin"
    assert result["meta_description"] == "Roofing repairs in Austin"
    assert result["public_phone"] == "512-555-0142"
    assert result["public_email"] == "hello@example.com"
    assert result["source_quality"] == "direct_business_website"


def test_contact_extraction_finds_public_fields():
    result = extract_contact_fields(
        "Apex Roofing serves Austin, TX. Call 512-555-0142 or hello@example.com.",
        "https://apex-roofing.example.com",
        "Apex Roofing",
    )

    assert result["company"] == "Apex Roofing"
    assert result["phone"] == "512-555-0142"
    assert result["email"] == "hello@example.com"
    assert result["city"] == "Austin"
    assert result["state"] == "TX"
    assert result["service_category"] == "roofing"


def test_source_validator_classifies_urls():
    assert classify_source("https://example-roofing.com/services", "roofing contact")["source_quality"] == "direct_business_website"
    assert classify_source("https://www.yelp.com/biz/apex-roofing")["source_quality"] == "directory_listing"
    assert classify_source("https://instagram.com/apexroofing")["source_quality"] == "social_profile"
    assert classify_source("https://apex.example.com", "Copyright 2020 Apex Roofing")["source_quality"] == "stale_source"
    assert classify_source("")["source_quality"] == "low_confidence"


def test_source_validator_scores_signal_quality():
    result = score_source(
        "https://apexridgeroofing-austin.test/services",
        "Apex Ridge Roofing serves Austin, TX since 2014. Call (512) 555-0142 or hello@example.com for storm damage roofing.",
        {"company": "Apex Ridge Roofing", "phone": "(512) 555-0142", "email": "hello@example.com"},
    )

    assert result["source_quality"] == "direct_business_website"
    assert result["domain_age_estimate"] == "established_10_plus_years"
    assert result["has_phone"] is True
    assert result["has_email"] is True
    assert result["has_location"] is True
    assert result["has_services_keywords"] is True
    assert result["detected_business_type"] == "roofing"
    assert result["confidence_score"] >= 80

    insurance = score_source(
        "https://harborshieldagency.test/contact",
        "Independent insurance agency for contractors and homeowners in Tampa, FL.",
        {"company": "Harbor Shield Insurance Agency", "service_category": "insurance"},
    )
    assert insurance["detected_business_type"] == "insurance"


def test_candidate_approval_does_not_create_contact_or_lead(monkeypatch):
    db = FakeDatabase()
    candidate_id = ObjectId()
    db.scraped_candidates.insert_one({"_id": candidate_id, "company": "Apex Roofing", "status": "needs_review", "source_url": "https://apex.example.com"})
    patch_database(monkeypatch, db)
    client = TestClient(app)

    response = client.post(f"/scraped-candidates/{candidate_id}/decision", json={"decision": "approve", "note": "Looks real"})

    assert response.status_code == 200
    assert db.scraped_candidates.documents[0]["status"] == "approved"
    assert db.contacts.documents == []
    assert db.leads.documents == []


def test_candidate_conversion_requires_prior_approval(monkeypatch):
    db = FakeDatabase()
    candidate_id = ObjectId()
    db.scraped_candidates.insert_one(
        {
            "_id": candidate_id,
            "company": "Apex Roofing",
            "status": "needs_review",
            "source_url": "https://apex.example.com",
            "confidence": 0.82,
            "source_quality": "direct_business_website",
            "module": "contractor_growth",
        }
    )
    patch_database(monkeypatch, db)
    client = TestClient(app)

    blocked = client.post(f"/scraped-candidates/{candidate_id}/decision", json={"decision": "convert_to_lead", "note": "Add to local pipeline"})
    assert blocked.status_code == 400
    assert db.leads.documents == []

    approved = client.post(f"/scraped-candidates/{candidate_id}/decision", json={"decision": "approve", "note": "Looks real"})
    assert approved.status_code == 200

    response = client.post(f"/scraped-candidates/{candidate_id}/decision", json={"decision": "convert_to_lead", "note": "Add to local pipeline"})

    assert response.status_code == 200
    assert db.scraped_candidates.documents[0]["status"] == "converted_to_lead"
    assert db.scraped_candidates.documents[0]["outbound_actions_taken"] == 0
    assert len(db.leads.documents) == 1
    assert db.leads.documents[0]["company_name"] == "Apex Roofing"
    assert db.leads.documents[0]["outreach_status"] == "not_started"
    assert db.contacts.documents == []


def test_candidate_insert_marks_duplicates_from_contacts():
    db = FakeDatabase()
    db.contacts.insert_one({"_id": ObjectId(), "company": "Apex Ridge Roofing", "phone": "5125550142", "source_url": "https://apexridgeroofing-austin.test"})

    candidate_ids = BaseTool().insert_candidates(
        db,
        [
            {
                "company": "Apex Ridge Roofing Co.",
                "phone": "(512) 555-0142",
                "source_url": "https://apexridgeroofing-austin.test/services",
                "raw_summary": "Roofing contractor in Austin, TX.",
            }
        ],
        create_approval=False,
    )

    assert len(candidate_ids) == 1
    stored = db.scraped_candidates.documents[0]
    assert stored["is_duplicate"] is True
    assert stored["duplicate_of"].startswith("contacts:")
    assert "phone" in stored["duplicate_reasons"]
    assert stored["quality_score"] < 100


def test_import_candidates_endpoint_creates_review_candidates(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    client = TestClient(app)
    csv_text = """company,website,phone,email,city,state,service_category,notes,source_url
Apex Import Roofing,https://apex-import.test,(512) 555-0111,hello@apex-import.test,Austin,TX,roofing,"Roof repair in Austin, TX since 2012.",https://apex-import.test
Northline Import HVAC,https://northline-import.test,303-555-0112,,Denver,CO,hvac,"Heating and air conditioning service in Denver, CO.",https://northline-import.test
"""

    response = client.post(
        "/tools/import-candidates",
        json={"module": "contractor_growth", "source_label": "manual_contractor_test", "csv_text": csv_text},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidate_count"] == 2
    assert payload["outbound_actions_taken"] == 0
    assert len(db.tool_runs.documents) == 1
    assert db.tool_runs.documents[0]["tool_name"] == "manual_upload"
    assert len(db.approval_requests.documents) == 2
    assert len(db.scraped_candidates.documents) == 2
    assert all(candidate["source"] == "manual_upload" for candidate in db.scraped_candidates.documents)
    assert all(candidate["source_label"] == "manual_contractor_test" for candidate in db.scraped_candidates.documents)
    assert all(candidate["status"] == "needs_review" for candidate in db.scraped_candidates.documents)
    assert db.contacts.documents == []
    assert db.leads.documents == []


def test_import_candidates_marks_duplicates_and_keeps_conversion_gated(monkeypatch):
    db = FakeDatabase()
    db.contacts.insert_one({"_id": ObjectId(), "company": "Apex Import Roofing", "phone": "5125550111", "source_url": "https://apex-import.test"})
    patch_database(monkeypatch, db)
    client = TestClient(app)
    csv_text = """company,website,phone,email,city,state,service_category,notes,source_url
Apex Import Roofing,https://apex-import.test,(512) 555-0111,hello@apex-import.test,Austin,TX,roofing,"Roof repair in Austin, TX.",https://apex-import.test
"""

    response = client.post(
        "/tools/import-candidates",
        json={"module": "contractor_growth", "source_label": "manual_contractor_test", "csv_text": csv_text},
    )

    assert response.status_code == 200
    stored = db.scraped_candidates.documents[0]
    assert stored["is_duplicate"] is True
    assert "phone" in stored["duplicate_reasons"]

    blocked = client.post(f"/scraped-candidates/{stored['_id']}/decision", json={"decision": "convert_to_contact", "note": "Convert locally"})
    assert blocked.status_code == 400
    assert len(db.contacts.documents) == 1

    approved = client.post(f"/scraped-candidates/{stored['_id']}/decision", json={"decision": "approve", "note": "Looks real"})
    assert approved.status_code == 200
    converted = client.post(f"/scraped-candidates/{stored['_id']}/decision", json={"decision": "convert_to_contact", "note": "Convert locally"})
    assert converted.status_code == 200
    assert db.scraped_candidates.documents[0]["status"] == "converted_to_contact"
    assert db.scraped_candidates.documents[0]["outbound_actions_taken"] == 0
    assert len(db.contacts.documents) == 2


def test_import_candidates_invalid_csv_fails_safely(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    client = TestClient(app)

    response = client.post(
        "/tools/import-candidates",
        json={"module": "contractor_growth", "source_label": "manual_contractor_test", "csv_text": "company,email\nOnly Name,hello@example.com\n"},
    )

    assert response.status_code == 400
    assert "missing required fields" in response.json()["detail"]
    assert db.scraped_candidates.documents == []
    assert db.contacts.documents == []
    assert db.leads.documents == []


def test_import_candidates_data_path_missing_fails_safely(monkeypatch):
    db = FakeDatabase()
    patch_database(monkeypatch, db)
    client = TestClient(app)

    response = client.post(
        "/tools/import-candidates",
        json={"module": "contractor_growth", "source_label": "manual_contractor_test", "csv_path": "data/imports/missing_sources.csv"},
    )

    assert response.status_code == 400
    assert "CSV file not found" in response.json()["detail"]
    assert db.scraped_candidates.documents == []


def test_manual_import_tool_rejects_empty_csv():
    try:
        ManualCandidateImportTool().parse_csv_text("", "contractor_growth", "manual_contractor_test")
    except ValueError as error:
        assert "empty" in str(error)
    else:
        raise AssertionError("Expected empty CSV to fail safely")


def test_tool_run_stores_no_secrets():
    db = FakeDatabase()
    BaseTool().record_tool_run(db, {"query": "roofing", "api_key": "secret", "token": "hidden"}, {"candidate_count": 0})

    stored_input = db.tool_runs.documents[0]["input"]
    assert stored_input == {"query": "roofing"}


def test_browser_scroll_reports_disabled_without_playwright(monkeypatch):
    monkeypatch.setattr("tools.browser_scroll_tool.robots_allowed", lambda _url: True)
    db = FakeDatabase()
    result = BrowserScrollTool().run("https://example.com", db=db)

    assert result["simulation_only"] is True
    assert result["candidate_ids"] == []
    assert "Playwright" in result["error"]
    assert db.tool_runs.documents[0]["status"] == "failed"
