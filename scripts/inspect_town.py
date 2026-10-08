"""Read-only inspection CLI for persisted LLM-Town JSON saves."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.simulation_inspector import SOURCES, compare, inspect, timeline

def main():
    parser = argparse.ArgumentParser(description="Inspect saved LLM-Town authority")
    sub = parser.add_subparsers(dest="command", required=True)
    t = sub.add_parser("timeline")
    t.add_argument("save")
    t.add_argument("--limit", type=int, default=50)
    t.add_argument("--offset", type=int, default=0)
    t.add_argument("--source", choices=sorted(SOURCES))
    i = sub.add_parser("show")
    i.add_argument("save")
    i.add_argument("scope", choices=["world", "resident", "relationship", "institution", "economy"])
    i.add_argument("--id")
    i.add_argument("--limit", type=int, default=50)
    c = sub.add_parser("compare")
    c.add_argument("left")
    c.add_argument("right")
    args = parser.parse_args()
    if args.command == "timeline":
        result = timeline(args.save, limit=args.limit, offset=args.offset,
                          kinds={args.source} if args.source else None)
    elif args.command == "show":
        result = inspect(args.save, scope=args.scope, identity=args.id,
                         limit=args.limit)
    else:
        result = compare(args.left, args.right)
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
