from __future__ import annotations

from urllib.parse import urlparse

from tools.base_tool import BaseTool, clean_text, robots_allowed, utc_now
from tools.contact_extraction_tool import extract_contact_fields
from tools.source_validator_tool import classify_source


class BrowserScrollTool(BaseTool):
    tool_name = "browser_scroll"

    def validate_url(self, public_url: str) -> str:
        public_url = clean_text(public_url)
        parsed = urlparse(public_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only public http(s) URLs are supported.")
        blocked_terms = ("login", "signin", "account", "checkout", "captcha", "paywall", "subscribe")
        if any(term in public_url.lower() for term in blocked_terms):
            raise ValueError("Protected, login, checkout, captcha, paywall, or gated URLs are not supported.")
        if not robots_allowed(public_url):
            raise ValueError("robots.txt does not allow this read-only browser fetch.")
        return public_url

    def capture(self, public_url: str, max_sections: int = 8) -> dict:
        public_url = self.validate_url(public_url)
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise RuntimeError("Playwright is not installed in this environment; browser scroll is disabled.") from exc

        sections: list[str] = []
        title = ""
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent="SignalForgeToolLayer/1.0 read-only")
            page.goto(public_url, wait_until="domcontentloaded", timeout=15000)
            title = clean_text(page.title())
            for index in range(max_sections):
                visible_text = page.locator("body").inner_text(timeout=5000)
                text = clean_text(visible_text)
                if text and text not in sections:
                    sections.append(text[:1800])
                page.evaluate("() => window.scrollBy(0, Math.max(window.innerHeight * 0.85, 600))")
                page.wait_for_timeout(250)
                at_bottom = page.evaluate("() => (window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 4)")
                if at_bottom:
                    break
            browser.close()

        combined_text = "\n\n".join(sections)
        fields = extract_contact_fields(combined_text, public_url, title)
        source = classify_source(public_url, combined_text)
        return {
            "source_url": public_url,
            "title": title,
            "visible_text_sections": sections,
            "section_count": len(sections),
            "extracted_fields": fields,
            "source_quality": source.get("source_quality"),
            "confidence": max(float(fields.get("confidence") or 0.0), float(source.get("confidence") or 0.0)),
            "fetched_at": utc_now().isoformat(),
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

    def run(self, public_url: str, max_sections: int = 8, db=None, agent_name: str | None = None, agent_run_id: str | None = None) -> dict:
        input_payload = {"public_url": public_url, "max_sections": max_sections}
        try:
            output = self.capture(public_url, max_sections=max_sections)
            output_summary = {
                "source_url": output.get("source_url"),
                "title": output.get("title"),
                "section_count": output.get("section_count"),
                "source_quality": output.get("source_quality"),
                "confidence": output.get("confidence"),
                "extracted_fields": output.get("extracted_fields"),
            }
            tool_run_id = self.record_tool_run(db, input_payload, output_summary, agent_name=agent_name, agent_run_id=agent_run_id)
            fields = output.get("extracted_fields") or {}
            candidate = {
                **fields,
                "source_url": output.get("source_url"),
                "source_quality": output.get("source_quality"),
                "confidence": output.get("confidence"),
                "raw_summary": "\n\n".join(output.get("visible_text_sections") or [])[:2000],
                "fetched_at": output.get("fetched_at"),
            }
            candidate_ids = self.insert_candidates(db, [candidate], tool_run_id, agent_name=agent_name, agent_run_id=agent_run_id)
            artifact_id = self.create_tool_artifact(db, tool_run_id, {"input": input_payload, "output": output, "candidate_ids": candidate_ids}, agent_name, agent_run_id)
            return {"tool_run_id": tool_run_id, "candidate_ids": candidate_ids, "artifact_id": artifact_id, "scroll": output, "simulation_only": True}
        except Exception as exc:
            tool_run_id = self.record_tool_run(db, input_payload, {}, status="failed", error=f"{exc.__class__.__name__}: {exc}", agent_name=agent_name, agent_run_id=agent_run_id)
            return {"tool_run_id": tool_run_id, "candidate_ids": [], "error": f"{exc.__class__.__name__}: {exc}", "simulation_only": True}


def scroll_public_page(public_url: str, max_sections: int = 8, db=None) -> dict:
    return BrowserScrollTool().run(public_url, max_sections=max_sections, db=db)
