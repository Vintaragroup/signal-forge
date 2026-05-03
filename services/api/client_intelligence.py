"""
Client Intelligence Module — SignalForge v9.5

Deterministic, rule-based intelligence generation.
No ML, no external calls, no publishing, no scheduling.

All outputs are:
    advisory_only = True
    simulation_only = True
    outbound_actions_taken = 0
"""

from __future__ import annotations

from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# ROI estimate
# ---------------------------------------------------------------------------

ROI_FACTOR = 12.5  # inferred value units per score point per record (advisory only)


def calculate_estimated_roi(perf_records: list[dict]) -> float:
    """Estimate ROI from performance records.

    Rule: avg_score × record_count × ROI_FACTOR
    ROI_FACTOR is a fixed inferred-value multiplier — no real financial data.
    Returns a float >= 0. Advisory only.
    """
    if not perf_records:
        return 0.0
    total_score = sum(float(r.get("performance_score") or 0) for r in perf_records)
    avg_score = total_score / len(perf_records)
    return round(avg_score * len(perf_records) * ROI_FACTOR, 2)


# ---------------------------------------------------------------------------
# Top-performer identification
# ---------------------------------------------------------------------------


def identify_top_performers(
    perf_records: list[dict],
    snippets: list[dict],
    campaign_reports: list[dict],
) -> dict:
    """Identify top-performing hooks, prompts, platforms, and themes.

    All logic is deterministic — Counter-based frequency + score weighting.
    Returns a dict with:
        top_hook_types, top_prompt_types, best_platforms,
        best_themes, top_snippet_ids
    """

    def _avg_score_ranking(groups: dict[str, list[float]]) -> list[str]:
        return sorted(
            groups.keys(),
            key=lambda k: sum(groups[k]) / len(groups[k]),
            reverse=True,
        )[:5]

    hook_scores: dict[str, list[float]] = {}
    prompt_scores: dict[str, list[float]] = {}
    platform_scores: dict[str, list[float]] = {}

    for r in perf_records:
        score = float(r.get("performance_score") or 0)
        if (hook := (r.get("hook_type") or "").strip()):
            hook_scores.setdefault(hook, []).append(score)
        if (pt := (r.get("prompt_type") or "").strip()):
            prompt_scores.setdefault(pt, []).append(score)
        if (plat := (r.get("platform") or "").strip()):
            platform_scores.setdefault(plat, []).append(score)

    # Best content themes from campaign reports
    theme_counter: Counter = Counter()
    for report in campaign_reports:
        for theme in (report.get("top_themes") or []):
            theme_counter[str(theme)] += 1
    best_themes = [t for t, _ in theme_counter.most_common(5)]

    # Top snippet IDs by overall_score
    sorted_snippets = sorted(
        snippets,
        key=lambda s: float(s.get("overall_score") or 0),
        reverse=True,
    )
    top_snippet_ids = [
        str(s["_id"]) for s in sorted_snippets[:10] if s.get("_id")
    ]

    return {
        "top_hook_types": _avg_score_ranking(hook_scores),
        "top_prompt_types": _avg_score_ranking(prompt_scores),
        "best_platforms": _avg_score_ranking(platform_scores),
        "best_themes": best_themes,
        "top_snippet_ids": top_snippet_ids,
    }


# ---------------------------------------------------------------------------
# Insight + recommendation text generation
# ---------------------------------------------------------------------------


def _derive_insights(perf_records: list[dict], top_performers: dict) -> list[str]:
    """Generate text insights from performance data. Advisory only."""
    insights: list[str] = []
    if not perf_records:
        insights.append(
            "No performance data available yet — log performance records to generate insights."
        )
        return insights

    avg_score = sum(float(r.get("performance_score") or 0) for r in perf_records) / len(perf_records)
    insights.append(
        f"Average content performance score: {round(avg_score, 2)} "
        f"across {len(perf_records)} records."
    )

    if top_performers.get("top_hook_types"):
        insights.append(
            f"Highest-performing hook type: '{top_performers['top_hook_types'][0]}'."
        )
    if top_performers.get("top_prompt_types"):
        insights.append(
            f"Most effective prompt type: '{top_performers['top_prompt_types'][0]}'."
        )
    if top_performers.get("best_platforms"):
        insights.append(
            f"Best-performing platform: '{top_performers['best_platforms'][0]}'."
        )

    high = [r for r in perf_records if float(r.get("performance_score") or 0) >= 7.0]
    low = [r for r in perf_records if float(r.get("performance_score") or 0) < 4.0]
    if high:
        insights.append(
            f"{len(high)} asset(s) scored ≥7.0 — strong performers to replicate."
        )
    if low:
        insights.append(
            f"{len(low)} asset(s) scored <4.0 — review for improvement opportunities."
        )

    return insights


def _derive_recommendations(top_performers: dict, perf_records: list[dict]) -> list[str]:
    """Generate actionable (advisory-only) recommendations."""
    recs: list[str] = []

    if top_performers.get("top_hook_types"):
        recs.append(
            f"Prioritise '{top_performers['top_hook_types'][0]}' hook type — "
            "highest avg performance score."
        )
    if top_performers.get("top_prompt_types"):
        recs.append(
            f"Use '{top_performers['top_prompt_types'][0]}' prompt type for the next content batch."
        )
    if top_performers.get("best_platforms"):
        recs.append(
            f"Focus distribution planning on '{top_performers['best_platforms'][0]}'."
        )
    if top_performers.get("best_themes"):
        recs.append(
            f"Content theme '{top_performers['best_themes'][0]}' showed strongest resonance — "
            "continue using it."
        )
    if not perf_records:
        recs.append(
            "Log manual performance data to unlock personalised recommendations."
        )

    recs.append(
        "All recommendations are advisory only. "
        "No automatic actions, posts, or messages will be triggered."
    )
    return recs


# ---------------------------------------------------------------------------
# Main intelligence builder
# ---------------------------------------------------------------------------


def build_client_intelligence(
    db: Any,
    client_id: str,
    workspace_slug: str,
) -> dict:
    """Build a full intelligence record for a client.

    Aggregates:
        - asset_performance_records (for client)
        - content_snippets (for workspace)
        - campaign_reports (for packs belonging to client)

    Derives: top performers, ROI estimate, insights, recommendations.
    Entirely deterministic — no ML, no external calls.

    Returns a dict suitable for inserting into client_intelligence_records.
    """
    perf_records = list(db.asset_performance_records.find({"client_id": client_id}))
    snippets = list(db.content_snippets.find({"workspace_slug": workspace_slug}))

    # Find campaign packs for this client, then their reports
    packs = list(db.campaign_packs.find({"client_id": client_id}))
    pack_ids = [str(p.get("_id", "")) for p in packs]
    campaign_reports = (
        list(db.campaign_reports.find({"campaign_pack_id": {"$in": pack_ids}}))
        if pack_ids
        else []
    )

    top_performers = identify_top_performers(perf_records, snippets, campaign_reports)
    estimated_roi = calculate_estimated_roi(perf_records)
    insights = _derive_insights(perf_records, top_performers)
    recommendations = _derive_recommendations(top_performers, perf_records)

    # Confidence score: based on data volume
    data_points = len(perf_records) + len(snippets) + len(campaign_reports)
    if data_points == 0:
        confidence_score = 0.0
    elif data_points < 5:
        confidence_score = 0.3
    elif data_points < 20:
        confidence_score = 0.6
    else:
        confidence_score = 0.9

    # Content performance score = avg of all perf record scores
    if perf_records:
        content_performance_score = round(
            sum(float(r.get("performance_score") or 0) for r in perf_records)
            / len(perf_records),
            2,
        )
    else:
        content_performance_score = 0.0

    # Pull acquisition info from client_profiles if present
    try:
        from bson import ObjectId as _ObjectId
        profile = db.client_profiles.find_one({"_id": _ObjectId(client_id)})
    except Exception:
        profile = None
    if not profile:
        profile = db.client_profiles.find_one({"_id": client_id}) or {}

    acquisition_score = float(profile.get("acquisition_score") or 0)
    source_lead_id = str(profile.get("source_lead_id") or "")

    return {
        "workspace_slug": workspace_slug,
        "client_id": client_id,
        "source_lead_id": source_lead_id,
        "acquisition_score": acquisition_score,
        "content_performance_score": content_performance_score,
        "top_snippet_ids": top_performers["top_snippet_ids"],
        "top_prompt_types": top_performers["top_prompt_types"],
        "top_hook_types": top_performers["top_hook_types"],
        "best_platforms": top_performers["best_platforms"],
        "estimated_roi": estimated_roi,
        "confidence_score": confidence_score,
        "insights": insights,
        "recommendations": recommendations,
        "simulation_only": True,
        "outbound_actions_taken": 0,
        "advisory_only": True,
    }


# ---------------------------------------------------------------------------
# Lead-to-content correlation
# ---------------------------------------------------------------------------


def correlate_lead_to_content_patterns(
    db: Any,
    workspace_slug: str,
    lead_id: str,
    client_id: str,
) -> list[dict]:
    """Correlate a lead's conversion to content performance patterns.

    Returns a list of correlation records — one per unique
    (content_theme, hook_type, prompt_type, platform) combination
    that has at least one performance record for the client.

    Sorted by descending performance_score. Advisory only.
    """
    correlations: list[dict] = []
    perf_records = list(db.asset_performance_records.find({"client_id": client_id}))
    if not perf_records:
        return correlations

    # Group by (content_theme, hook_type, prompt_type, platform)
    groups: dict[tuple, list[float]] = {}
    for r in perf_records:
        key = (
            (r.get("content_theme") or "").strip(),
            (r.get("hook_type") or "").strip(),
            (r.get("prompt_type") or "").strip(),
            (r.get("platform") or "").strip(),
        )
        groups.setdefault(key, []).append(float(r.get("performance_score") or 0))

    for (content_theme, hook_type, prompt_type, platform), scores in groups.items():
        avg_score = sum(scores) / len(scores)
        if avg_score >= 5.0:
            strength = "strong"
        elif avg_score >= 3.0:
            strength = "moderate"
        else:
            strength = "weak"

        correlations.append({
            "workspace_slug": workspace_slug,
            "lead_id": lead_id,
            "client_id": client_id,
            "content_theme": content_theme,
            "hook_type": hook_type,
            "prompt_type": prompt_type,
            "platform": platform,
            "performance_score": round(avg_score, 2),
            "correlation_strength": strength,
            "correlation_notes": (
                f"{len(scores)} performance record(s). "
                f"Avg score: {round(avg_score, 2)}. "
                f"Strength: {strength}. Advisory only."
            ),
            "simulation_only": True,
            "outbound_actions_taken": 0,
            "advisory_only": True,
        })

    return sorted(correlations, key=lambda c: c["performance_score"], reverse=True)
