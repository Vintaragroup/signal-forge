from __future__ import annotations

from urllib.parse import urlparse
import re

from tools.base_tool import BaseTool, clean_text


DIRECT_HINTS = {"about", "services", "contact", "roofing", "hvac", "contractor", "insurance", "media", "music"}
DIRECTORY_DOMAINS = {"yelp.com", "angi.com", "thumbtack.com", "bbb.org", "yellowpages.com", "homeadvisor.com"}
SOCIAL_DOMAINS = {"facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com", "tiktok.com", "youtube.com"}
STALE_YEAR_RE = re.compile(r"\b(?:copyright|updated|since)\s*(20(?:1[0-9]|20|21|22))\b")


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


def classify_source(source_url: str, page_text: str = "") -> dict:
    return SourceValidatorTool().classify(source_url, page_text)
