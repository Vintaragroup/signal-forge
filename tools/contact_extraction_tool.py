from __future__ import annotations

import re
from urllib.parse import urlparse

from tools.base_tool import BaseTool, clean_text


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")
CITY_STATE_RE = re.compile(r"\b([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){0,2}),\s*([A-Z]{2})\b")
SERVICE_KEYWORDS = ["roofing", "hvac", "plumbing", "contractor", "insurance", "media", "music", "marketing", "construction"]


class ContactExtractionTool(BaseTool):
    tool_name = "contact_extraction"

    def extract(self, text: str, source_url: str = "", title: str = "") -> dict:
        body = clean_text(text)
        email_match = EMAIL_RE.search(body)
        phone_match = PHONE_RE.search(body)
        location_match = CITY_STATE_RE.search(body)
        parsed = urlparse(clean_text(source_url))
        host_name = parsed.netloc.removeprefix("www.").split(".")[0].replace("-", " ").title() if parsed.netloc else ""
        title_name = clean_text(title).split("|")[0].split("-")[0].strip()
        company = title_name or host_name
        lower_body = body.lower()
        service_category = next((keyword for keyword in SERVICE_KEYWORDS if keyword in lower_body or keyword in company.lower()), "unknown")
        confidence = 0.2
        confidence += 0.2 if company else 0
        confidence += 0.2 if email_match else 0
        confidence += 0.2 if phone_match else 0
        confidence += 0.1 if location_match else 0
        confidence += 0.1 if source_url else 0
        return {
            "company": company,
            "phone": phone_match.group(0) if phone_match else "",
            "email": email_match.group(0) if email_match else "",
            "city": location_match.group(1).strip() if location_match else "",
            "state": location_match.group(2) if location_match else "",
            "service_category": service_category,
            "website": clean_text(source_url),
            "source_url": clean_text(source_url),
            "confidence": round(min(confidence, 0.95), 2),
        }


def extract_contact_fields(text: str, source_url: str = "", title: str = "") -> dict:
    return ContactExtractionTool().extract(text, source_url, title)
