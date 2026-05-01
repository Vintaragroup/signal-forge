# SignalForge Agent Tool Layer v1 - Phase 1

This folder contains the first safe research-tool foundation for SignalForge agents and operators.

Phase 1 tools are read-only and review-first:

- no form submission
- no login
- no posting
- no messaging
- no captcha bypass
- no protected or private scraping
- no browser scrolling
- no real search API
- no automatic contact or lead creation

Tool outputs may create `scraped_candidates` with `status=needs_review`. Operators must explicitly approve, reject, or convert a candidate through the API or dashboard before any local contact or lead record is created.

## Tools

- `web_search_tool.py`: mock search only; creates candidate source records from deterministic seed data.
- `website_scraper_tool.py`: fetches a public URL and extracts title, meta description, headings, visible text summary, and public phone/email when present.
- `contact_extraction_tool.py`: extracts possible company, phone, email, city, state, service category, website, source URL, and confidence from public text.
- `source_validator_tool.py`: classifies source quality as `direct_business_website`, `directory_listing`, `social_profile`, `unknown`, or `low_confidence`.

## CLI

```bash
python scripts/run_tool.py web_search --query "roofing contractor" --module contractor_growth --location "Austin, TX" --limit 3
python scripts/run_tool.py website_scraper --url https://example.com
```

All tool runs are recorded in `tool_runs`. Candidate records are stored in `scraped_candidates` for review.
