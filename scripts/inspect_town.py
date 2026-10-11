"""Read-only inspection CLI for persisted LLM-Town JSON saves."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.inspection_presentation import format_trace
from src.analysis.causal_inspector import trace
from src.analysis.causal_evidence import COLLECTIONS
from src.analysis.inspection_save import InspectionError
from src.analysis.simulation_inspector import SOURCES, compare, inspect, timeline

def main() -> None:
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
    tr = sub.add_parser("trace")
    tr.add_argument("save")
    tr.add_argument("--type", choices=sorted([*COLLECTIONS, "civic_activity"]), required=True)
    tr.add_argument("--id", required=True)
    tr.add_argument("--format", choices=["json", "text"], default="json")
    tr.add_argument("--depth", type=int, default=6)
    tr.add_argument("--limit", type=int, default=100)
    tr.add_argument("--direction", choices=['upstream', 'downstream', 'both'], default='both')
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
    elif args.command == "trace":
        result = trace(args.save, type=args.type, identity=args.id, depth=args.depth,
                       limit=args.limit, direction=args.direction)
    else:
        result = compare(args.left, args.right)
    if args.command == 'trace' and args.format == 'text':
        print(format_trace(result))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    try:
        main()
    except (InspectionError, ValueError) as error:
        print(json.dumps({'error': str(error), 'kind': 'inspection_error', 'schema_version': 1}), file=sys.stderr)
        raise SystemExit(2)
