# SignalForge Agent Tool Layer v1

This folder contains the safe research-tool foundation for SignalForge agents and operators.

Tools are read-only and review-first:

- no form submission
- no login
- no posting
- no messaging
- no captcha bypass
- no protected or private scraping
- no real search API
- no automatic contact or lead creation

Tool outputs may create `scraped_candidates` with `status=needs_review`, linked `agent_artifacts`, and approval requests. Operators must approve a candidate before converting it into a local contact or lead record.

## Tools

- `web_search_tool.py`: deterministic mock search; `SERPAPI_KEY` is recorded as future support but no live search API is called in v1.
- `website_scraper_tool.py`: fetches a public URL and extracts title, meta description, headings, visible text summary, and public phone/email when present.
- `browser_scroll_tool.py`: uses Playwright when installed to scroll public pages and capture visible text sections without clicking gated or submit elements.
- `contact_extraction_tool.py`: extracts possible company, phone, email, city, state, service category, website, source URL, and confidence from public text.
- `source_validator_tool.py`: classifies source quality as `direct_business_website`, `directory_listing`, `social_profile`, `stale_source`, `unknown`, or `low_confidence`.

## CLI

```bash
python scripts/run_tool.py web_search --query "roofing contractor" --module contractor_growth --location "Austin, TX" --limit 3
python scripts/run_tool.py website_scraper --url https://example.com
python scripts/run_tool.py browser_scroll --url https://example.com
```

All tool runs are recorded in `tool_runs` with sanitized inputs, source URLs, extracted fields, confidence, and optional linked agent run IDs. Candidate records are stored in `scraped_candidates` for review.
