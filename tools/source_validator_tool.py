from __future__ import annotations

from urllib.parse import urlparse
import re

from tools.base_tool import BaseTool, clean_text


DIRECT_HINTS = {"about", "services", "contact", "roofing", "hvac", "contractor", "insurance", "media", "music"}
DIRECTORY_DOMAINS = {"yelp.com", "angi.com", "thumbtack.com", "bbb.org", "yellowpages.com", "homeadvisor.com"}
SOCIAL_DOMAINS = {"facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com", "tiktok.com", "youtube.com"}
STALE_YEAR_RE = re.compile(r"\b(?:copyright|updated)\s*(20(?:1[0-9]|20|21|22))\b")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}")
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
CITY_STATE_RE = re.compile(r"\b([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){0,2}),\s*([A-Z]{2})\b")
STATE_CITY_RE = re.compile(r"\b([A-Z]{2})\s*[-|/]\s*([A-Z][a-zA-Z.'-]*(?:\s+[A-Z][a-zA-Z.'-]*){0,2})\b")
SERVICE_KEYWORDS = {
    "roofing": ["roof", "roofing", "shingle", "metal roof", "storm damage", "gutter"],
    "hvac": ["hvac", "air conditioning", "heating", "furnace", "cooling"],
    "plumbing": ["plumbing", "plumber", "drain", "water heater", "sewer"],
    "contractor": ["contractor", "construction", "remodel", "renovation", "builder"],
    "insurance": ["insurance", "policy", "coverage", "agency", "claim"],
    "media": ["media", "production", "podcast", "video", "studio", "press"],
    "music": ["music", "artist", "song", "tour", "album", "fan"],
    "marketing": ["marketing", "seo", "campaign", "creative", "brand"],
}


def service_keywords_for_text(text: str) -> list[str]:
    lower_text = clean_text(text).lower()
    matches: list[str] = []
    for keywords in SERVICE_KEYWORDS.values():
        for keyword in keywords:
            if keyword in lower_text and keyword not in matches:
                matches.append(keyword)
    return matches


def business_type_for_keywords(keywords: list[str], fallback: str = "unknown") -> str:
    fallback_type = clean_text(fallback).lower()
    if fallback_type and fallback_type != "unknown" and fallback_type in SERVICE_KEYWORDS:
        return fallback_type
    keyword_set = set(keywords)
    for business_type, terms in SERVICE_KEYWORDS.items():
        if keyword_set.intersection(terms):
            return business_type
    return clean_text(fallback) or "unknown"


def detect_location(text: str, fields: dict | None = None) -> dict:
    fields = fields or {}
    city = clean_text(fields.get("city"))
    state = clean_text(fields.get("state")).upper()
    if city and state:
        return {"city": city, "state": state, "has_location": True}
    body = clean_text(text)
    city_state = CITY_STATE_RE.search(body)
    if city_state:
        return {"city": city_state.group(1).strip(), "state": city_state.group(2).upper(), "has_location": True}
    state_city = STATE_CITY_RE.search(body)
    if state_city:
        return {"city": state_city.group(2).strip(), "state": state_city.group(1).upper(), "has_location": True}
    return {"city": city, "state": state, "has_location": bool(city or state)}


def estimate_domain_age(source_url: str, page_text: str = "") -> str:
    parsed = urlparse(clean_text(source_url))
    host = parsed.netloc.lower().removeprefix("www.")
    text = clean_text(page_text).lower()
    since_match = re.search(r"\b(?:since|est\.?|established)\s*(19\d{2}|20\d{2})\b", text)
    if since_match:
        year = int(since_match.group(1))
        return "established_10_plus_years" if year <= 2016 else "established_3_plus_years"
    if any(token in host for token in ("near-me", "best", "top", "directory", "leads")):
        return "newer_or_directory_like"
    if host and any(hint in host for hint in DIRECT_HINTS):
        return "established_heuristic"
    return "unknown"


def score_source_quality(source_url: str, page_text: str = "", fields: dict | None = None, duplicate: bool = False) -> dict:
    fields = fields or {}
    text = " ".join(clean_text(value) for value in [page_text, fields.get("company"), fields.get("service_category"), fields.get("source_url")])
    service_keywords = service_keywords_for_text(text)
    location = detect_location(text, fields)
    has_phone = bool(clean_text(fields.get("phone")) or PHONE_RE.search(text))
    has_email = bool(clean_text(fields.get("email")) or EMAIL_RE.search(text))
    has_location = location["has_location"]
    has_services_keywords = bool(service_keywords)
    domain_age_estimate = estimate_domain_age(source_url, page_text)
    classification = SourceValidatorTool().classify(source_url, page_text)
    score = 20
    score += 18 if classification["source_quality"] == "direct_business_website" else 10 if classification["source_quality"] in {"directory_listing", "social_profile"} else 0
    score += 15 if has_phone else 0
    score += 15 if has_email else 0
    score += 12 if has_location else 0
    score += 12 if has_services_keywords else 0
    score += 8 if domain_age_estimate.startswith("established") else -5 if domain_age_estimate == "newer_or_directory_like" else 0
    score -= 30 if duplicate else 0
    score = max(0, min(100, score))
    return {
        **classification,
        "domain_age_estimate": domain_age_estimate,
        "has_phone": has_phone,
        "has_email": has_email,
        "has_location": has_location,
        "has_services_keywords": has_services_keywords,
        "service_keywords": service_keywords,
        "detected_business_type": business_type_for_keywords(service_keywords, fields.get("service_category") or "unknown"),
        "detected_city": location.get("city", ""),
        "detected_state": location.get("state", ""),
        "confidence_score": score,
        "confidence": round(score / 100, 2),
    }


class SourceValidatorTool(BaseTool):
    tool_name = "source_validator"

    def classify(self, source_url: str, page_text: str = "") -> dict:
        source_url = clean_text(source_url)
        parsed = urlparse(source_url)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        text = clean_text(page_text).lower()
        if not source_url or not host:
            quality = "low_confidence"
            confidence = 0.1
        elif STALE_YEAR_RE.search(text):
            quality = "stale_source"
            confidence = 0.25
        elif any(host == domain or host.endswith(f".{domain}") for domain in DIRECTORY_DOMAINS):
            quality = "directory_listing"
            confidence = 0.75
        elif any(host == domain or host.endswith(f".{domain}") for domain in SOCIAL_DOMAINS):
            quality = "social_profile"
            confidence = 0.7
        elif any(hint in host or hint in path or hint in text for hint in DIRECT_HINTS):
            quality = "direct_business_website"
            confidence = 0.85
        else:
            quality = "unknown"
            confidence = 0.4
        return {"source_url": source_url, "source_quality": quality, "confidence": confidence}

    def score(self, source_url: str, page_text: str = "", fields: dict | None = None, duplicate: bool = False) -> dict:
        return score_source_quality(source_url, page_text, fields, duplicate)


def classify_source(source_url: str, page_text: str = "") -> dict:
    return SourceValidatorTool().classify(source_url, page_text)


def score_source(source_url: str, page_text: str = "", fields: dict | None = None, duplicate: bool = False) -> dict:
    return SourceValidatorTool().score(source_url, page_text, fields, duplicate)
