import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.base_agent import SUPPORTED_MODULES
from agents.content_agent import ContentAgent
from agents.fan_engagement_agent import FanEngagementAgent
from agents.followup_agent import FollowupAgent
from agents.outreach_agent import OutreachAgent


AGENTS = {
    "outreach": OutreachAgent,
    "content": ContentAgent,
    "fan_engagement": FanEngagementAgent,
    "followup": FollowupAgent,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simulation-only SignalForge agent.")
    parser.add_argument("agent", choices=sorted(AGENTS), help="Agent to run")
    parser.add_argument("--module", required=True, choices=sorted(SUPPORTED_MODULES), help="Module context")
    parser.add_argument("--dry-run", action="store_true", help="Print and log planned actions only")
    parser.add_argument("--limit", type=int, default=10, help="Maximum Mongo records to inspect")
    parser.add_argument("--mongo-uri", default=None, help="MongoDB URI override")
    parser.add_argument("--vault", default=None, help="Vault path override")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    agent_cls = AGENTS[args.agent]
    agent = agent_cls(
        module=args.module,
        dry_run=True if args.dry_run else True,
        mongo_uri=args.mongo_uri,
        vault_path=args.vault,
        limit=args.limit,
    )
    if not args.dry_run:
        print("Simulation mode is enforced; running as dry-run.")
    agent.run()


if __name__ == "__main__":
    main()
