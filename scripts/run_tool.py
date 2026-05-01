import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_DIR = PROJECT_ROOT / "services" / "api"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

from main import get_client, get_database
from tools.web_search_tool import WebSearchTool
from tools.website_scraper_tool import WebsiteScraperTool


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safe SignalForge research tools in review-only mode.")
    subparsers = parser.add_subparsers(dest="tool", required=True)

    search_parser = subparsers.add_parser("web_search", help="Run mock web search and create review candidates.")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--module", default="contractor_growth")
    search_parser.add_argument("--location", default="")
    search_parser.add_argument("--limit", type=int, default=5)

    scraper_parser = subparsers.add_parser("website_scraper", help="Fetch a public website and create a review candidate.")
    scraper_parser.add_argument("--url", required=True)

    args = parser.parse_args()
    client = get_client()
    try:
        db = get_database(client)
        if args.tool == "web_search":
            result = WebSearchTool().run(args.query, args.module, args.location, args.limit, db=db)
        else:
            result = WebsiteScraperTool().run(args.url, db=db)
    finally:
        client.close()

    print("SignalForge Tool Layer v1 - Phase 1")
    print("Safety: read-only research. No forms, login, posting, messaging, captcha bypass, or protected scraping.")
    print(f"Tool run: {result.get('tool_run_id') or 'not recorded'}")
    print(f"Candidates created: {len(result.get('candidate_ids') or [])}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    else:
        for candidate_id in result.get("candidate_ids") or []:
            print(f"- scraped_candidate {candidate_id} status=needs_review")


if __name__ == "__main__":
    main()
