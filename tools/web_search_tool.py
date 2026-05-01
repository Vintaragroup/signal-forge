from __future__ import annotations

from tools.base_tool import BaseTool, clean_text, slugify, utc_now


MOCK_BUSINESSES = [
    {"company": "Mock Apex Roofing", "city": "Austin", "state": "TX", "service_category": "roofing", "website": "https://mock-apex-roofing.example.invalid", "phone": "512-555-0142", "email": "hello@mock-apex-roofing.example.invalid"},
    {"company": "Mock Northline HVAC", "city": "Denver", "state": "CO", "service_category": "hvac", "website": "https://mock-northline-hvac.example.invalid", "phone": "303-555-0198", "email": "info@mock-northline-hvac.example.invalid"},
    {"company": "Mock Harbor Insurance", "city": "Tampa", "state": "FL", "service_category": "insurance", "website": "https://mock-harbor-insurance.example.invalid", "phone": "813-555-0164", "email": "team@mock-harbor-insurance.example.invalid"},
    {"company": "Mock Studio Media", "city": "Nashville", "state": "TN", "service_category": "media", "website": "https://mock-studio-media.example.invalid", "phone": "615-555-0120", "email": "press@mock-studio-media.example.invalid"},
]


class WebSearchTool(BaseTool):
    tool_name = "web_search"
    mode = "mock_read_only"

    def search(self, query: str, module: str, location: str = "", limit: int = 5) -> list[dict]:
        query_text = clean_text(query).lower()
        location_text = clean_text(location).lower()
        scored = []
        for business in MOCK_BUSINESSES:
            haystack = " ".join(str(value).lower() for value in business.values())
            score = 0.45
            score += 0.25 if any(term in haystack for term in query_text.split()) else 0
            score += 0.15 if location_text and any(term in haystack for term in location_text.replace(",", " ").split()) else 0
            score += 0.1 if clean_text(module).replace("_growth", "") in haystack else 0
            scored.append((score, business))
        scored.sort(key=lambda item: item[0], reverse=True)
        candidates = []
        for score, business in scored[: max(1, min(int(limit or 5), 25))]:
            candidates.append(
                {
                    **business,
                    "candidate_key": slugify(f"mock-{business['company']}-{business['city']}-{business['state']}"),
                    "module": clean_text(module),
                    "query": clean_text(query),
                    "location": clean_text(location),
                    "source_url": business["website"],
                    "source_quality": "direct_business_website",
                    "confidence": round(min(score, 0.95), 2),
                    "raw_summary": f"Mock search candidate for {business['company']} from query '{clean_text(query)}'.",
                    "is_mock": True,
                    "timestamp": utc_now(),
                }
            )
        return candidates

    def run(self, query: str, module: str, location: str = "", limit: int = 5, db=None) -> dict:
        input_payload = {"query": query, "module": module, "location": location, "limit": limit, "mode": "mock"}
        candidates = self.search(query, module, location, limit)
        tool_run_id = self.record_tool_run(db, input_payload, {"candidate_count": len(candidates), "mode": "mock"})
        candidate_ids = self.insert_candidates(db, candidates, tool_run_id)
        return {"tool_run_id": tool_run_id, "candidate_ids": candidate_ids, "candidates": candidates, "simulation_only": True}


def run_mock_search(query: str, module: str, location: str = "", limit: int = 5, db=None) -> dict:
    return WebSearchTool().run(query, module, location, limit, db)
