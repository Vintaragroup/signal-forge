"""Phase 6D/6E — Discovery Intelligence Engine

Generates discovery insights from real Tavily web search (topic="news",
recency + relevance filtered — see get_real_social_trends()), existing
workflow data, heuristic scoring, and (Phase 6E) configured client sources.
Gated behind TAVILY_ENABLED/TAVILY_API_KEY; returns no insights (not mock
ones) when disabled or unconfigured — same fallback precedent as every
other real integration in this codebase.
Safe to call multiple times — each call generates a fresh batch tagged with source_run_id.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

# ── Asset type display labels ──────────────────────────────────────────────────
ASSET_TYPE_LABELS: dict[str, str] = {
    "script_draft": "Script Draft",
    "video_prompt": "Video Prompt",
    "carousel_outline": "Carousel Outline",
    "linkedin_post": "LinkedIn Post",
    "newsletter_section": "Newsletter Section",
    "social_caption": "Social Caption",
    "content_brief": "Content Brief",
    "outreach_email": "Outreach Email",
}


# ── Utility ────────────────────────────────────────────────────────────────────

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Signal collection (real search) ─────────────────────────────────────────────

_PLATFORM_DOMAINS: dict[str, str] = {
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "instagram.com": "Instagram",
    "linkedin.com": "LinkedIn",
    "twitter.com": "X",
    "x.com": "X",
    "facebook.com": "Facebook",
    "threads.net": "Threads",
    "reddit.com": "Reddit",
    "pinterest.com": "Pinterest",
}


def _infer_platform_from_url(url: str) -> str:
    """Best-effort platform label from a result URL's hostname. Not a
    verified source — just enough to populate evidence.platform honestly
    from what the URL actually says, same spirit as
    trend_discovery_agent.py's _best_effort_creator_handle()."""
    try:
        from urllib.parse import urlparse  # noqa: PLC0415

        host = (urlparse(url).hostname or "").lower()
        host = host[4:] if host.startswith("www.") else host
        for domain, label in _PLATFORM_DOMAINS.items():
            if host == domain or host.endswith("." + domain):
                return label
    except Exception:
        pass
    return "Web"


def _clean_search_snippet(text: str, max_len: int = 400) -> str:
    """Best-effort cleanup of Tavily's raw scraped page content.

    Real-world pages (especially JS-heavy social platforms like TikTok/
    Instagram) often come back as raw nav chrome and UI labels mixed with
    the actual content — "TikTok Log in Search For You Explore Following
    LIVE Upload Profile More ...". This is heuristic cleanup, not real NLP
    extraction: drop short non-sentence lines (nav labels, like/comment
    counts), drop exact-duplicate lines, collapse whitespace, and truncate
    to a readable length at a word boundary. It will not catch everything —
    some redundancy/cruft can still slip through — but it removes most of
    the unreadable chrome without fabricating or rewriting real content.
    """
    if not text:
        return ""

    seen: set[str] = set()
    kept: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or line in seen:
            continue
        if line.replace(",", "").replace(".", "").isdigit():
            continue  # like/comment/view counters
        word_count = len(line.split())
        if word_count < 4 and not line.endswith((".", "!", "?")):
            continue  # likely a nav label, not a sentence
        seen.add(line)
        kept.append(line)

    cleaned = " ".join(" ".join(kept).split()) if kept else " ".join(text.split())
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return cleaned


def get_real_social_trends(
    module: str,
    workspace_slug: str,
    client_profile_slug: str | None,
    db: Any,
    max_results: int = 4,
) -> list[dict]:
    """Real, Tavily-search-derived trend signals, shaped identically to what
    the former mock catalog produced so score_opportunity()/
    derive_quality_tags()/build_evidence()/build_recommendation() work
    unchanged. Gated behind TAVILY_ENABLED/TAVILY_API_KEY via
    tavily_client.search() — returns [] (not fabricated data) when
    disabled, unconfigured, or no results clear the relevance floor.

    client_profile_slug is accepted for signature compatibility but not
    used to filter client_profiles — every current caller passes None, and
    the working real pipeline (agents/trend_discovery_agent.py) already
    filters by workspace_slug only.
    """
    from tavily_client import search as tavily_search  # noqa: PLC0415

    try:
        from agents.base_agent import SUPPORTED_MODULES  # noqa: PLC0415

        module_label = SUPPORTED_MODULES.get(module, {}).get("label", "") or module.replace("_", " ").title()
    except Exception:
        module_label = module.replace("_", " ").title()

    profile: dict[str, Any] = {}
    try:
        profile = db.client_profiles.find_one({"workspace_slug": workspace_slug}) or {}
    except Exception:
        profile = {}

    audience = (profile.get("audience") or "").strip()
    content_goals = (profile.get("content_goals") or "").strip()
    is_generic_fallback = not audience and not content_goals

    parts = [module_label]
    if audience:
        parts.append(f"content relevant to: {audience}")
    if content_goals:
        parts.append(f"aligned with goal: {content_goals}")
    if is_generic_fallback:
        parts.append("trending audience content this week")
    query = " — ".join(parts)

    result = tavily_search(query, max_results=max_results, topic="news", days=30, min_score=0.3)
    if result.get("simulated") or not result.get("results"):
        return []

    rationale = f"Discovered via Tavily search for '{query}'."
    if is_generic_fallback:
        rationale = (
            "Warning: client profile has no audience/content_goals set, so this used a generic "
            "fallback query and may be less targeted than usual. " + rationale
        )

    trends: list[dict] = []
    for item in result["results"]:
        url = item.get("url", "")
        if not url:
            continue
        trends.append({
            "id": hashlib.sha1(url.encode()).hexdigest()[:12],
            "keyword": query,
            "title": item.get("title") or url,
            "summary": _clean_search_snippet(item.get("content") or ""),
            "insight_type": "content_opportunity",
            "platforms": [_infer_platform_from_url(url)],
            "asset_types": ["content_brief"],
            "next_stage": "generate_content",
            "rationale": rationale,
            "base_score": float(item.get("score") or 0.0),
            "signal_type": "search_trend",
            "source_url": url,
        })
    return trends


def get_recent_workflow_assets(workspace_slug: str, db: Any) -> list[dict]:
    """Return the 50 most recent workflow assets for this workspace."""
    try:
        cursor = (
            db.workflow_assets
            .find({"workspace_slug": workspace_slug})
            .sort([("created_at", -1)])
            .limit(50)
        )
        return list(cursor)
    except Exception:
        return []


def get_recent_approved_content(workspace_slug: str, db: Any) -> list[dict]:
    """Return approved workflow assets for this workspace."""
    try:
        cursor = (
            db.workflow_assets
            .find({"workspace_slug": workspace_slug, "approval_state": "approved"})
            .sort([("created_at", -1)])
            .limit(30)
        )
        return list(cursor)
    except Exception:
        return []


# Phase 6E: map from source_type to canonical platform name used in recommendations
_SOURCE_TYPE_TO_PLATFORM: dict[str, str] = {
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "youtube": "YouTube Shorts",
    "tiktok": "TikTok",
    "x": "X (Twitter)",
    "facebook": "Facebook",
    "podcast": "Podcast",
    "rss_feed": "Podcast",
    "website": "Website",
    "google_drive": "Google Drive",
    "dropbox": "Dropbox",
    "media_library": "Media Library",
}


def get_configured_sources(workspace_slug: str, client_profile_slug: str | None, db: Any) -> list[dict]:
    """Return active configured client_sources for this workspace/profile.

    Used to make discovery recommendations client-aware by injecting real
    platform context into evidence and recommendation fields.
    Returns empty list on any failure (non-blocking).
    """
    try:
        query: dict[str, Any] = {"workspace_slug": workspace_slug, "status": "active"}
        if client_profile_slug:
            query["client_profile_slug"] = client_profile_slug
        cursor = db.client_sources.find(query).limit(50)
        return list(cursor)
    except Exception:
        return []


def get_existing_insight_keywords(workspace_slug: str, db: Any) -> set[str]:
    """Return lowercase keywords from existing discovery insights (for recurrence tagging)."""
    try:
        cursor = (
            db.discovery_insights
            .find({"workspace_slug": workspace_slug})
            .sort([("created_at", -1)])
            .limit(30)
        )
        keywords: set[str] = set()
        for doc in cursor:
            for ev in doc.get("evidence") or []:
                kw = (ev.get("keyword") or "").strip().lower()
                if kw:
                    keywords.add(kw)
        return keywords
    except Exception:
        return set()


# ── Scoring ────────────────────────────────────────────────────────────────────

def _keyword_in_text(keyword: str, text: str) -> bool:
    """Return True if any significant word (>4 chars) from keyword appears in text."""
    significant = [w.lower() for w in keyword.split() if len(w) > 4]
    text_lower = text.lower()
    return any(w in text_lower for w in significant)


def score_opportunity(
    trend: dict,
    approved_content: list[dict],
    existing_insight_keywords: set[str] | None = None,
) -> float:
    """Compute a 0.0–1.0 confidence score for a discovery opportunity.

    Factors:
      - base_score defined in the trend catalogue
      - +0.07 bonus when prior approved content matches the trend keyword
      - +0.05 bonus for 3+ platform signal; +0.02 for 2-platform signal
    Always clamps to [0.0, 1.0].
    """
    score = float(trend.get("base_score", 0.6))
    keyword = trend.get("keyword", "")

    # Bonus: prior approved content with similar keywords
    has_prior_match = any(
        _keyword_in_text(keyword, a.get("title", "") + " " + a.get("summary", ""))
        for a in approved_content
    )
    if has_prior_match:
        score = min(1.0, score + 0.07)

    # Bonus: multi-platform signal
    platform_count = len(trend.get("platforms", []))
    if platform_count >= 3:
        score = min(1.0, score + 0.05)
    elif platform_count >= 2:
        score = min(1.0, score + 0.02)

    return round(min(1.0, max(0.0, score)), 3)


def derive_quality_tags(
    trend: dict,
    confidence: float,
    approved_content: list[dict],
    existing_insight_keywords: set[str] | None = None,
) -> list[str]:
    """Derive display quality tags for an insight card.

    Possible tags:
      - "High Confidence"       — score ≥ 0.85
      - "Multi-Platform Signal" — recommendation covers ≥ 2 platforms
      - "Based on Prior Success" — a prior approved asset matches this keyword
      - "Recurring Trend"       — keyword already seen in existing insights
      - "Fresh Signal"          — keyword not yet seen (complement of Recurring)
    """
    tags: list[str] = []
    keyword = trend.get("keyword", "")

    if confidence >= 0.85:
        tags.append("High Confidence")

    if len(trend.get("platforms", [])) >= 2:
        tags.append("Multi-Platform Signal")

    has_prior_match = any(
        _keyword_in_text(keyword, a.get("title", "") + " " + a.get("summary", ""))
        for a in approved_content
    )
    if has_prior_match:
        tags.append("Based on Prior Success")

    kw_lower = keyword.lower()
    if existing_insight_keywords and kw_lower in existing_insight_keywords:
        tags.append("Recurring Trend")
    else:
        tags.append("Fresh Signal")

    return tags


# ── Recommendation builder ────────────────────────────────────────────────────

def build_recommendation(
    trend: dict,
    module: str,
    configured_sources: list[dict] | None = None,
) -> dict:
    """Build a DiscoveryRecommendation-shaped dict from a trend signal.

    Phase 6E: when configured_sources are provided, the recommended_platforms
    list is augmented to prioritise platforms the client actually has connected,
    and a note is added to the rationale when sources match.
    """
    base_platforms: list[str] = list(trend.get("platforms", []))
    rationale: str = trend.get("rationale", "")

    if configured_sources:
        connected_platforms: list[str] = []
        for src in configured_sources:
            canonical = _SOURCE_TYPE_TO_PLATFORM.get(src.get("source_type", ""), "")
            if canonical and canonical not in connected_platforms:
                connected_platforms.append(canonical)

        # Boost platforms the client actually has — move them to front
        boosted: list[str] = [p for p in connected_platforms if p in base_platforms]
        remaining: list[str] = [p for p in base_platforms if p not in boosted]
        final_platforms = boosted + remaining

        # Add podcast context if RSS/podcast source present and relevant
        podcast_src = next(
            (s for s in configured_sources if s.get("source_type") in ("podcast", "rss_feed")), None
        )
        if podcast_src and "Podcast" not in final_platforms and trend.get("insight_type") in (
            "content_opportunity",
            "authority_signal",
        ):
            final_platforms.append("Podcast")
            rationale = rationale + " Client has a configured podcast/RSS source — long-form clips are recommended."

        if connected_platforms:
            rationale = (
                rationale
                + f" Configured sources connected: {', '.join(connected_platforms[:3])}."
            ).strip()
    else:
        final_platforms = base_platforms

    return {
        "recommended_asset_types": list(trend.get("asset_types", [])),
        "recommended_platforms": final_platforms,
        "recommended_next_stage": trend.get("next_stage", "generate_content"),
        "rationale": rationale,
    }


# ── Evidence builder ──────────────────────────────────────────────────────────

def build_evidence(
    trend: dict,
    configured_sources: list[dict] | None = None,
) -> list[dict]:
    """Build evidence items from a trend signal.

    Phase 6E: when configured_sources are provided, matching active sources
    are annotated onto evidence items with source_label, source_type, and
    configured_source=True so the UI can show 'Derived From Configured Sources'.
    """
    evidence: list[dict] = []
    platforms = trend.get("platforms", [])

    # Build a quick lookup: canonical_platform -> first matching source
    source_by_platform: dict[str, dict] = {}
    if configured_sources:
        for src in configured_sources:
            canonical = _SOURCE_TYPE_TO_PLATFORM.get(src.get("source_type", ""), "")
            if canonical and canonical not in source_by_platform:
                source_by_platform[canonical] = src

    # Primary signal evidence
    primary: dict[str, Any] = {
        "signal_type": trend.get("signal_type", "search_trend"),
        "keyword": trend.get("keyword"),
        "growth_pct": trend.get("growth_pct"),
        "notes": trend.get("rationale") or (
            f"{trend.get('insight_type', 'opportunity')} detected via discovery analysis."
        ),
        "source_label": None,
        "source_type": None,
        "configured_source": False,
    }
    if trend.get("metric"):
        primary["metric"] = trend["metric"]
    if trend.get("value") is not None:
        primary["value"] = float(trend["value"])
    if trend.get("source_url"):
        primary["source_url"] = trend["source_url"]
    if platforms:
        primary["platform"] = platforms[0]
        matched_src = source_by_platform.get(platforms[0])
        if matched_src:
            primary["source_label"] = matched_src.get("label")
            primary["source_type"] = matched_src.get("source_type")
            primary["configured_source"] = True

    evidence.append(primary)

    # Secondary platform evidence when multi-platform
    if len(platforms) >= 2:
        sec: dict[str, Any] = {
            "platform": platforms[1],
            "signal_type": "platform_overlap",
            "keyword": trend.get("keyword"),
            "notes": f"Signal confirmed on {platforms[1]} — multi-platform opportunity.",
            "source_label": None,
            "source_type": None,
            "configured_source": False,
        }
        matched_src2 = source_by_platform.get(platforms[1])
        if matched_src2:
            sec["source_label"] = matched_src2.get("label")
            sec["source_type"] = matched_src2.get("source_type")
            sec["configured_source"] = True
        evidence.append(sec)

    return evidence


# ── Asset generation helper ───────────────────────────────────────────────────

def asset_docs_from_insight(insight: dict, now: datetime | None = None) -> list[dict]:
    """Create placeholder workflow_asset documents from a discovery insight.

    Returns a list of dicts ready for insertion into workflow_assets.
    Caps at 3 asset types (first three from the recommendation).
    """
    if now is None:
        now = _utc_now()

    rec = insight.get("recommendation") or {}
    asset_types: list[str] = (rec.get("recommended_asset_types") or [])[:3]
    if not asset_types:
        asset_types = ["content_brief"]

    insight_id_str = str(insight.get("_id", ""))
    workspace = insight.get("workspace_slug", "")

    docs: list[dict] = []
    for asset_type in asset_types:
        label = ASSET_TYPE_LABELS.get(asset_type, asset_type.replace("_", " ").title())
        docs.append(
            {
                "run_id": f"discovery-{insight_id_str}",
                "title": f"{insight.get('title', 'Discovery Asset')} — {label}",
                "asset_type": asset_type,
                "summary": (insight.get("summary") or "")[:300],
                "approval_state": "needs_review",
                "distribution_state": "not_queued",
                "source_discovery_insight_id": insight_id_str,
                "workspace_slug": workspace,
                "created_at": now,
                "updated_at": now,
            }
        )
    return docs


# ── Main pipeline ──────────────────────────────────────────────────────────────

def generate_discovery_insights(
    db: Any,
    workspace_slug: str,
    client_profile_slug: str | None,
    module: str,
    source_run_id: str | None = None,
    max_insights: int = 4,
) -> list[dict]:
    """Orchestrate discovery intelligence generation.

    Pipeline:
      1. Collect real, Tavily-search-derived trend signals for the module
      2. Load recent approved content for prior-success context
      3. Load existing insight keywords for recurrence detection
      4. Score and rank each opportunity
      5. Derive quality tags, evidence, and recommendation
      6. Persist insights to discovery_insights collection
      7. Return created insight dicts (with _id populated)

    Non-fatal: individual insert failures are swallowed so that a single
    bad document never fails the whole batch.
    """
    now = _utc_now()
    trends = get_real_social_trends(module, workspace_slug, client_profile_slug, db, max_results=max_insights)
    approved_content = get_recent_approved_content(workspace_slug, db)
    existing_kws = get_existing_insight_keywords(workspace_slug, db)
    # Phase 6E: fetch configured client sources to make discovery client-aware
    configured_sources = get_configured_sources(workspace_slug, client_profile_slug, db)

    # Score all trends and take the top N
    scored = sorted(
        ((score_opportunity(t, approved_content, existing_kws), t) for t in trends),
        key=lambda x: x[0],
        reverse=True,
    )
    top_trends = scored[:max_insights]

    created: list[dict] = []
    for confidence, trend in top_trends:
        tags = derive_quality_tags(trend, confidence, approved_content, existing_kws)
        evidence = build_evidence(trend, configured_sources=configured_sources)
        recommendation = build_recommendation(trend, module, configured_sources=configured_sources)

        doc: dict[str, Any] = {
            "workspace_slug": workspace_slug,
            "client_profile_slug": client_profile_slug,
            "insight_type": trend.get("insight_type", "content_opportunity"),
            "title": trend["title"],
            "summary": trend["summary"],
            "confidence_score": confidence,
            "evidence": evidence,
            "recommendation": recommendation,
            "quality_tags": tags,
            "source_agent": "discovery_engine",
            "source_run_id": source_run_id,
            "linked_workflow_asset_ids": [],
            "status": "pending_review",
            "approved_by": None,
            "approved_at": None,
            "created_at": now,
            "updated_at": now,
        }

        try:
            result = db.discovery_insights.insert_one(doc)
            doc["_id"] = result.inserted_id
            created.append(doc)
            # Track this keyword so subsequent iterations in the same run tag correctly
            kw = trend.get("keyword", "").lower()
            if kw:
                existing_kws.add(kw)
        except Exception:
            pass  # Non-fatal: skip failed document

    return created
