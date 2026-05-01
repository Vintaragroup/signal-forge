from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib import error, request
from urllib.parse import urlparse

from tools.base_tool import BaseTool, clean_text, robots_allowed, utc_now
from tools.contact_extraction_tool import extract_contact_fields
from tools.source_validator_tool import classify_source


class PublicPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_description = ""
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self._tag_stack: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag == "meta" and attrs_dict.get("name", "").lower() == "description":
            self.meta_description = clean_text(attrs_dict.get("content"))

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data):
        if self._skip:
            return
        text = clean_text(data)
        if not text:
            return
        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        if current_tag == "title":
            self.title = clean_text(f"{self.title} {text}")
        elif current_tag in {"h1", "h2", "h3"}:
            self.headings.append(text)
            self.text_parts.append(text)
        else:
            self.text_parts.append(text)


class WebsiteScraperTool(BaseTool):
    tool_name = "website_scraper"

    def validate_url(self, public_url: str) -> None:
        parsed = urlparse(public_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only public http/https URLs are supported.")
        if any(term in public_url.lower() for term in ("login", "signin", "account", "checkout", "captcha")):
            raise ValueError("Protected, login, checkout, or captcha URLs are not supported.")
        if not robots_allowed(public_url):
            raise ValueError("robots.txt does not allow this read-only fetch.")

    def parse_html(self, html: str, source_url: str) -> dict:
        parser = PublicPageParser()
        parser.feed(html)
        visible_text = " ".join(parser.text_parts)
        visible_text = re.sub(r"\s+", " ", visible_text).strip()
        extracted = extract_contact_fields(visible_text, source_url, parser.title)
        source = classify_source(source_url, visible_text)
        return {
            "source_url": source_url,
            "fetched_at": utc_now(),
            "title": parser.title,
            "meta_description": parser.meta_description,
            "headings": parser.headings[:12],
            "visible_text_summary": visible_text[:800],
            "public_phone": extracted.get("phone", ""),
            "public_email": extracted.get("email", ""),
            "extracted_fields": extracted,
            "confidence": max(extracted.get("confidence", 0), source.get("confidence", 0)),
            "source_quality": source["source_quality"],
        }

    def fetch(self, public_url: str) -> dict:
        public_url = clean_text(public_url)
        self.validate_url(public_url)
        http_request = request.Request(public_url, headers={"User-Agent": "SignalForgeToolLayer/1.0 read-only"}, method="GET")
        with request.urlopen(http_request, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                raise ValueError("URL did not return public HTML content.")
            html = response.read(1_000_000).decode("utf-8", errors="ignore")
        return self.parse_html(html, public_url)

    def run(self, public_url: str, db=None, agent_name: str | None = None, agent_run_id: str | None = None) -> dict:
        input_payload = {"public_url": public_url}
        try:
            output = self.fetch(public_url)
            output_summary = {"source_url": public_url, "title": output.get("title"), "source_quality": output.get("source_quality"), "confidence": output.get("confidence"), "extracted_fields": output.get("extracted_fields")}
            tool_run_id = self.record_tool_run(db, input_payload, output_summary, agent_name=agent_name, agent_run_id=agent_run_id)
            candidate = {
                **output.get("extracted_fields", {}),
                "source_url": output["source_url"],
                "source_quality": output["source_quality"],
                "confidence": output["confidence"],
                "raw_summary": output["visible_text_summary"],
                "fetched_at": output["fetched_at"],
            }
            candidate_ids = self.insert_candidates(db, [candidate], tool_run_id, agent_name=agent_name, agent_run_id=agent_run_id)
            artifact_id = self.create_tool_artifact(db, tool_run_id, {"input": input_payload, "output": output, "candidate_ids": candidate_ids}, agent_name, agent_run_id)
            return {"tool_run_id": tool_run_id, "candidate_ids": candidate_ids, "artifact_id": artifact_id, "scrape": output, "simulation_only": True}
        except Exception as exc:
            self.record_tool_run(db, input_payload, {}, status="failed", error=f"{exc.__class__.__name__}: {exc}", agent_name=agent_name, agent_run_id=agent_run_id)
            return {"tool_run_id": None, "candidate_ids": [], "error": f"{exc.__class__.__name__}: {exc}", "simulation_only": True}
