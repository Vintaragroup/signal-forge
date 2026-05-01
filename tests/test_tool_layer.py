from bson import ObjectId
from fastapi.testclient import TestClient

import main
from main import app
from tools.contact_extraction_tool import extract_contact_fields
from tools.source_validator_tool import classify_source
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
    assert classify_source("")["source_quality"] == "low_confidence"


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


def test_candidate_conversion_requires_explicit_decision(monkeypatch):
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

    response = client.post(f"/scraped-candidates/{candidate_id}/decision", json={"decision": "convert_to_lead", "note": "Add to local pipeline"})

    assert response.status_code == 200
    assert db.scraped_candidates.documents[0]["status"] == "converted_to_lead"
    assert db.scraped_candidates.documents[0]["outbound_actions_taken"] == 0
    assert len(db.leads.documents) == 1
    assert db.leads.documents[0]["company_name"] == "Apex Roofing"
    assert db.leads.documents[0]["outreach_status"] == "not_started"
    assert db.contacts.documents == []
