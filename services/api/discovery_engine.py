"""
Phase 6D — Discovery Intelligence Engine

Generates discovery insights from mock signal sources, existing workflow data,
and heuristic scoring. No external APIs, scraping, or credentials required.
All trend signals are deterministic and seeded by module + workspace context.
Safe to call multiple times — each call generates a fresh batch tagged with source_run_id.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

# ── Mock trend catalog ─────────────────────────────────────────────────────────
MOCK_TRENDS: dict[str, list[dict]] = {
    "media_growth": [
        {
            "id": "executive_burnout",
            "keyword": "executive burnout recovery",
            "title": "Executive burnout content outperforming standard leadership advice on LinkedIn",
            "summary": (
                "Vulnerability-forward burnout narratives are consistently outperforming conventional leadership "
                "content by 3–4x on LinkedIn. Audiences are seeking authenticity and operational honesty "
                "from senior leaders, not polished advice."
            ),
            "insight_type": "content_opportunity",
            "platforms": ["LinkedIn", "YouTube Shorts"],
            "asset_types": ["script_draft", "linkedin_post", "video_prompt"],
            "next_stage": "generate_content",
            "rationale": (
                "Search demand for burnout recovery from executives has risen 34% over 90 days. "
                "Competing creators in this niche have low production quality — high upside for authority content."
            ),
            "base_score": 0.88,
            "signal_type": "search_trend",
            "metric": "monthly_searches",
            "value": 48200.0,
            "growth_pct": 34.5,
        },
        {
            "id": "contradiction_hooks",
            "keyword": "leadership contradiction hooks short-form",
            "title": "Short-form contradiction hooks outperforming long-form clips on YouTube Shorts",
            "summary": (
                "Hooks that open with a counter-intuitive leadership claim — 'The decision that cost me $2M was "
                "the best one I made' — are driving 4–6x average completion rates compared to advice-forward openers."
            ),
            "insight_type": "content_format",
            "platforms": ["YouTube Shorts", "TikTok", "Instagram"],
            "asset_types": ["script_draft", "video_prompt"],
            "next_stage": "generate_content",
            "rationale": (
                "Contradiction hook formats have grown 28% month-over-month on short-form platforms. "
                "Completion rates favour counter-intuitive claims over advice-first content."
            ),
            "base_score": 0.82,
            "signal_type": "format_trend",
            "metric": "avg_completion_rate_delta",
            "value": 4.3,
            "growth_pct": 28.0,
        },
        {
            "id": "decision_fatigue_carousel",
            "keyword": "decision fatigue carousel framework",
            "title": "Decision fatigue carousels gaining saves and shares on Instagram",
            "summary": (
                "Carousel posts exploring cognitive load and decision-making frameworks are generating "
                "high save rates on Instagram — particularly when they include actionable frameworks or checklists."
            ),
            "insight_type": "content_opportunity",
            "platforms": ["Instagram", "LinkedIn"],
            "asset_types": ["carousel_outline", "linkedin_post"],
            "next_stage": "generate_content",
            "rationale": (
                "Decision fatigue as a topic sees consistent organic growth with low competition in the "
                "executive coaching and leadership space. Save-heavy content builds long-term reach."
            ),
            "base_score": 0.75,
            "signal_type": "engagement_signal",
            "metric": "save_rate_delta",
            "value": 2.8,
            "growth_pct": 21.0,
        },
        {
            "id": "operational_clarity_series",
            "keyword": "operational clarity founder transparency",
            "title": "Operational clarity and business transparency series building long-term authority",
            "summary": (
                "Founders and operators sharing real operational data, decision logs, and business clarity posts "
                "are building outsized authority in their niche. Audiences favour transparency over polished messaging."
            ),
            "insight_type": "authority_signal",
            "platforms": ["LinkedIn", "Podcast"],
            "asset_types": ["linkedin_post", "newsletter_section", "script_draft"],
            "next_stage": "generate_content",
            "rationale": (
                "Transparency-driven content consistently outperforms promotional content in B2B audiences. "
                "This format creates compounding authority and trust-building without paid promotion."
            ),
            "base_score": 0.79,
            "signal_type": "engagement_signal",
            "metric": "authority_score_delta",
            "value": 3.1,
            "growth_pct": 18.5,
        },
        {
            "id": "what_i_wish_i_knew",
            "keyword": "what I wish I knew as a founder",
            "title": "'What I wish I knew' retrospective format gaining traction on YouTube Shorts",
            "summary": (
                "Retrospective formats — where experienced operators share hindsight lessons — are consistently "
                "top-performing on YouTube Shorts and LinkedIn. They resonate strongly with early-stage founders "
                "and aspiring operators."
            ),
            "insight_type": "content_format",
            "platforms": ["YouTube Shorts", "LinkedIn"],
            "asset_types": ["script_draft", "video_prompt", "carousel_outline"],
            "next_stage": "generate_content",
            "rationale": (
                "The 'what I wish I knew' format leverages high-authority positioning while appealing "
                "to aspirational audiences. Short-form videos using this format see 22% higher shares."
            ),
            "base_score": 0.77,
            "signal_type": "format_trend",
            "metric": "share_rate_delta",
            "value": 1.8,
            "growth_pct": 22.0,
        },
    ],
    "artist_growth": [
        {
            "id": "fan_connection_bts",
            "keyword": "artist behind the scenes fan connection",
            "title": "Behind-the-scenes fan connection content driving streaming uplift",
            "summary": (
                "Artists sharing authentic creation process content — studio sessions, songwriting breakdowns, "
                "personal narratives — are seeing measurable streaming and follower growth."
            ),
            "insight_type": "content_opportunity",
            "platforms": ["Instagram", "TikTok", "YouTube Shorts"],
            "asset_types": ["video_prompt", "script_draft", "social_caption"],
            "next_stage": "generate_content",
            "rationale": (
                "Fan connection content builds parasocial loyalty and increases repeat streaming behaviour. "
                "Audiences are rewarding transparency with saves, shares, and follows."
            ),
            "base_score": 0.84,
            "signal_type": "engagement_signal",
            "metric": "follower_growth_rate",
            "value": 12.5,
            "growth_pct": 31.0,
        },
        {
            "id": "release_countdown_series",
            "keyword": "artist release countdown engagement series",
            "title": "Release countdown content series compounding pre-release engagement",
            "summary": (
                "Artists using structured countdown content (30/20/10/3/1 day formats) are seeing "
                "significantly higher first-week streaming numbers than single-announcement releases."
            ),
            "insight_type": "content_format",
            "platforms": ["Instagram", "TikTok", "Twitter/X"],
            "asset_types": ["social_caption", "carousel_outline", "video_prompt"],
            "next_stage": "generate_content",
            "rationale": (
                "Structured countdown campaigns create anticipation loops and repeat platform signals, "
                "boosting algorithmic reach at the moment of release."
            ),
            "base_score": 0.80,
            "signal_type": "format_trend",
            "metric": "pre_release_engagement_delta",
            "value": 2.6,
            "growth_pct": 26.0,
        },
        {
            "id": "collaboration_cross_promo",
            "keyword": "artist collaboration cross-promotion audience",
            "title": "Cross-promotion collaboration content multiplying audience reach",
            "summary": (
                "Collaboration content between artists in adjacent genres is consistently outperforming "
                "solo promotional content — especially when each creator genuinely endorses the other."
            ),
            "insight_type": "audience_signal",
            "platforms": ["Instagram", "YouTube Shorts", "TikTok"],
            "asset_types": ["video_prompt", "script_draft"],
            "next_stage": "generate_content",
            "rationale": (
                "Genre-adjacent collaboration creates new audience overlap without cannibalising existing fans. "
                "Cross-promo posts see 2x average reach compared to solo content."
            ),
            "base_score": 0.72,
            "signal_type": "engagement_signal",
            "metric": "reach_multiplier",
            "value": 2.1,
            "growth_pct": 19.0,
        },
    ],
    "contractor_growth": [
        {
            "id": "spring_home_prep",
            "keyword": "spring home maintenance checklist",
            "title": "Spring home preparation queries spiking — peak local search volume of the year",
            "summary": (
                "Seasonal search queries for home maintenance services are at their annual peak. "
                "Contractors publishing timely content around spring preparation are capturing "
                "high-intent homeowners actively seeking service providers."
            ),
            "insight_type": "seasonal_signal",
            "platforms": ["Google My Business", "Facebook", "Instagram"],
            "asset_types": ["content_brief", "linkedin_post", "social_caption"],
            "next_stage": "generate_content",
            "rationale": (
                "Seasonal intent spikes create a narrow window for first-mover advantage "
                "in local search and social. Publishing now maximises visibility before competitors."
            ),
            "base_score": 0.87,
            "signal_type": "search_trend",
            "metric": "monthly_searches",
            "value": 32400.0,
            "growth_pct": 41.0,
        },
        {
            "id": "before_after_transformation",
            "keyword": "contractor before after project transformation",
            "title": "Before/after transformation posts generating highest contractor engagement rates",
            "summary": (
                "Before/after project documentation posts are consistently the highest-performing "
                "content format for local contractors — 3x average engagement versus service listing posts."
            ),
            "insight_type": "content_format",
            "platforms": ["Instagram", "Facebook", "TikTok"],
            "asset_types": ["content_brief", "social_caption", "video_prompt"],
            "next_stage": "generate_content",
            "rationale": (
                "Visual transformation content activates social proof and drives referral enquiries "
                "from local audiences. Authenticity outperforms polish."
            ),
            "base_score": 0.83,
            "signal_type": "engagement_signal",
            "metric": "engagement_rate_multiplier",
            "value": 3.2,
            "growth_pct": 33.0,
        },
        {
            "id": "homeowner_pain_point",
            "keyword": "homeowner pain point service education",
            "title": "Pain-point-first content outperforming promotional posts for contractor leads",
            "summary": (
                "Content that opens with a homeowner frustration or problem — 'Why your HVAC breaks every winter' — "
                "is generating 4x more enquiries than promotional service listings."
            ),
            "insight_type": "content_opportunity",
            "platforms": ["Facebook", "Instagram"],
            "asset_types": ["content_brief", "social_caption"],
            "next_stage": "generate_content",
            "rationale": (
                "Pain-point framing creates immediate relevance and positions the contractor "
                "as the trusted solution provider before any pitch is made."
            ),
            "base_score": 0.76,
            "signal_type": "engagement_signal",
            "metric": "enquiry_rate_delta",
            "value": 4.1,
            "growth_pct": 25.0,
        },
    ],
    "insurance_growth": [
        {
            "id": "cyber_risk_awareness",
            "keyword": "small business cyber insurance coverage",
            "title": "Cyber risk awareness content seeing 40% search growth following recent breach news",
            "summary": (
                "Small business owners are actively searching for cyber insurance information following "
                "high-profile breach incidents. Educational content explaining coverage gaps is gaining "
                "significant organic traction."
            ),
            "insight_type": "content_opportunity",
            "platforms": ["LinkedIn", "Google My Business", "Email newsletter"],
            "asset_types": ["newsletter_section", "linkedin_post", "content_brief"],
            "next_stage": "generate_content",
            "rationale": (
                "Real-time search demand spike creates a narrow window to establish authority "
                "and capture high-intent enquiries before the news cycle moves on."
            ),
            "base_score": 0.86,
            "signal_type": "search_trend",
            "metric": "monthly_searches",
            "value": 28600.0,
            "growth_pct": 40.0,
        },
        {
            "id": "life_event_triggers",
            "keyword": "insurance life event new business home purchase",
            "title": "Life event trigger content driving highest-quality insurance enquiries",
            "summary": (
                "Content connected to life events — new business formation, home purchase, growing family — "
                "is consistently generating the highest-quality insurance leads. Audiences in these moments "
                "have high intent and low price sensitivity."
            ),
            "insight_type": "audience_signal",
            "platforms": ["LinkedIn", "Facebook", "Email newsletter"],
            "asset_types": ["newsletter_section", "content_brief", "outreach_email"],
            "next_stage": "generate_content",
            "rationale": (
                "Life event triggers create natural, non-pushy insurance conversations and attract "
                "prospects at the ideal decision moment."
            ),
            "base_score": 0.81,
            "signal_type": "audience_signal",
            "metric": "lead_quality_score",
            "value": 8.4,
            "growth_pct": 23.0,
        },
    ],
}

# Fallback for unknown modules
MOCK_TRENDS["_default"] = MOCK_TRENDS["media_growth"][:3]

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


def _seed_float(seed_str: str, lo: float = 0.0, hi: float = 1.0) -> float:
    """Deterministic float in [lo, hi) derived from a string seed."""
    digest = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    return lo + (digest % 100_000) / 100_000 * (hi - lo)


# ── Signal collection ──────────────────────────────────────────────────────────

def get_mock_social_trends(module: str) -> list[dict]:
    """Return the mock trend signals for a given module.

    Returns a non-empty list for any module — falls back to _default.
    """
    return list(MOCK_TRENDS.get(module, MOCK_TRENDS["_default"]))


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

def build_recommendation(trend: dict, module: str) -> dict:
    """Build a DiscoveryRecommendation-shaped dict from a trend signal."""
    return {
        "recommended_asset_types": list(trend.get("asset_types", [])),
        "recommended_platforms": list(trend.get("platforms", [])),
        "recommended_next_stage": trend.get("next_stage", "generate_content"),
        "rationale": trend.get("rationale", ""),
    }


# ── Evidence builder ──────────────────────────────────────────────────────────

def build_evidence(trend: dict) -> list[dict]:
    """Build evidence items from a trend signal."""
    evidence: list[dict] = []
    platforms = trend.get("platforms", [])

    # Primary signal evidence
    primary: dict[str, Any] = {
        "signal_type": trend.get("signal_type", "search_trend"),
        "keyword": trend.get("keyword"),
        "growth_pct": trend.get("growth_pct"),
        "notes": (
            f"Simulated signal — {trend.get('insight_type', 'opportunity')} "
            "detected via discovery analysis."
        ),
    }
    if trend.get("metric"):
        primary["metric"] = trend["metric"]
    if trend.get("value") is not None:
        primary["value"] = float(trend["value"])
    if platforms:
        primary["platform"] = platforms[0]

    evidence.append(primary)

    # Secondary platform evidence when multi-platform
    if len(platforms) >= 2:
        evidence.append({
            "platform": platforms[1],
            "signal_type": "platform_overlap",
            "keyword": trend.get("keyword"),
            "notes": f"Signal confirmed on {platforms[1]} — multi-platform opportunity.",
        })

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
      1. Collect mock trend signals for the module
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
    trends = get_mock_social_trends(module)
    approved_content = get_recent_approved_content(workspace_slug, db)
    existing_kws = get_existing_insight_keywords(workspace_slug, db)

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
        evidence = build_evidence(trend)
        recommendation = build_recommendation(trend, module)

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
