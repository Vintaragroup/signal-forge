from datetime import datetime, timezone
from typing import Any

from agents.base_agent import BaseAgent


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


MIN_RELEVANCE_SCORE = 0.0


class TrendDiscoveryAgent(BaseAgent):
    """Phase 6Z — real trend/demographic content discovery.

    Searches for content relevant to the client's audience via Tavily
    (read-only web search, gated behind TAVILY_ENABLED/TAVILY_API_KEY), then
    creates `source_content` documents (status=needs_review,
    content_rights=third_party_curated) so discovered candidates flow into
    the existing Creative Studio review → clip → render pipeline unchanged.

    This agent never downloads media, never posts, and never approves its
    own discoveries — every created source_content record and every planned
    action still goes through the standard human-approval gate.
    """

    agent_name = "trend_discovery"
    agent_role = "Discover audience-relevant trending content for curation review"

    def plan_actions(self, leads: list[dict]) -> list[dict[str, str]]:
        tavily_search = self._import_tavily_search()

        profile = self._fetch_client_profile()
        query = self._build_query(profile)

        result = tavily_search(query, max_results=self.limit or 5)

        if self.db is not None and self.run_id:
            self.record_step(
                self.db,
                self.run_id,
                10,
                "tavily_trend_search",
                {"query": query, "max_results": self.limit or 5},
                "Read-only web search for audience-relevant trending content. No download, no posting.",
                {
                    "simulated": result.get("simulated"),
                    "skip_reason": result.get("skip_reason"),
                    "result_count": len(result.get("results") or []),
                },
            )

        if result.get("simulated") or not result.get("results"):
            return [
                {
                    "title": "No trend discovery results",
                    "target": self.module,
                    "reason": result.get("skip_reason")
                    or "Tavily returned no results for this query.",
                    "planned_action": (
                        "No source_content candidates were created. "
                        "Enable TAVILY_ENABLED + TAVILY_API_KEY, or broaden the client "
                        "profile's audience/content_goals, and re-run this agent."
                    ),
                }
            ]

        created = self._create_source_content_candidates(result["results"], query)

        actions: list[dict[str, str]] = []
        for item in created:
            actions.append(
                {
                    "title": f"Review curated content candidate: {item['title'] or item['source_url']}",
                    "target": item["source_url"],
                    "reason": item["discovery_reason"],
                    "planned_action": (
                        "Approve or reject via PATCH /source-content/{id}/status before any "
                        f"clipping, download, or reuse. Attribution: {item['attribution_caption']}."
                    ),
                }
            )
        return actions

    # ------------------------------------------------------------------
    # Import bootstrap
    # ------------------------------------------------------------------

    @staticmethod
    def _import_tavily_search():
        """Import tavily_client.search across all runtime layouts.

        Docker (services/api/*.py flat-copied to /app/, PYTHONPATH=/app) and
        the pytest suite (which inserts services/api onto sys.path) resolve a
        flat `import tavily_client` directly. `scripts/run_agent.py` only
        puts the repo root on sys.path, so fall back to inserting
        services/api explicitly for that local-CLI case.
        """
        try:
            from tavily_client import search as tavily_search  # noqa: PLC0415

            return tavily_search
        except ImportError:
            import sys
            from pathlib import Path

            services_api_dir = Path(__file__).resolve().parents[1] / "services" / "api"
            if str(services_api_dir) not in sys.path:
                sys.path.insert(0, str(services_api_dir))
            from tavily_client import search as tavily_search  # noqa: PLC0415

            return tavily_search

    # ------------------------------------------------------------------
    # Query building
    # ------------------------------------------------------------------

    def _fetch_client_profile(self) -> dict[str, Any]:
        if self.db is None:
            return {}
        query: dict[str, Any] = {}
        if self.workspace_slug:
            query["workspace_slug"] = self.workspace_slug
        else:
            return {}
        try:
            return self.db.client_profiles.find_one(query) or {}
        except Exception:
            return {}

    def _build_query(self, profile: dict[str, Any]) -> str:
        audience = clean_text(profile.get("audience"))
        content_goals = clean_text(profile.get("content_goals"))
        module_label = self.module_config["label"]

        parts = [module_label]
        if audience:
            parts.append(f"content relevant to: {audience}")
        if content_goals:
            parts.append(f"aligned with goal: {content_goals}")
        if not audience and not content_goals:
            parts.append("trending audience content this week")
        return " — ".join(parts)

    # ------------------------------------------------------------------
    # source_content bridge
    # ------------------------------------------------------------------

    def _create_source_content_candidates(
        self, results: list[dict[str, Any]], query: str
    ) -> list[dict[str, Any]]:
        if self.db is None:
            return []

        now = datetime.now(timezone.utc)
        created: list[dict[str, Any]] = []

        for result in results:
            source_url = clean_text(result.get("url"))
            if not source_url:
                continue

            title = clean_text(result.get("title")) or source_url
            creator_handle = self._best_effort_creator_handle(source_url)
            attribution_caption = (
                f"Content via {creator_handle}" if creator_handle else f"Content via {source_url}"
            )
            discovery_reason = (
                f"Discovered via Tavily search for '{query}'. "
                "Creator attribution is best-effort from the source URL — "
                "verify and correct before use."
            )
            score = result.get("score")
            discovery_score = float(score) if isinstance(score, (int, float)) else 0.0

            doc: dict[str, Any] = {
                "workspace_slug": self.workspace_slug,
                "client_id": "",
                "source_channel_id": "",
                "platform": "",
                "source_url": source_url,
                "title": title,
                "creator": creator_handle or "",
                "published_at": clean_text(result.get("published_date")),
                "duration_seconds": 0,
                "performance_metadata": {},
                "discovery_score": discovery_score,
                "discovery_reason": discovery_reason,
                "status": "needs_review",
                "content_rights": "third_party_curated",
                "creator_handle": creator_handle or "",
                "creator_platform_url": source_url,
                "attribution_caption": attribution_caption,
                "review_events": [],
                "simulation_only": True,
                "outbound_actions_taken": 0,
                "generated_by_agent": self.agent_name,
                "agent_run_id": self.run_id,
                "created_at": now,
                "updated_at": now,
            }
            try:
                insert_result = self.db.source_content.insert_one(doc)
                doc["_id"] = insert_result.inserted_id
            except Exception:
                continue

            created.append(doc)

        return created

    @staticmethod
    def _best_effort_creator_handle(source_url: str) -> str:
        """Derive a display-only creator label from a URL's hostname.

        Not a verified identity — operators must confirm real attribution
        during review before any content is clipped or reused.
        """
        try:
            from urllib.parse import urlparse

            hostname = urlparse(source_url).hostname or ""
            return hostname.replace("www.", "")
        except Exception:
            return ""
