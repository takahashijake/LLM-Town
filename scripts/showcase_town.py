#!/usr/bin/env python3
"""Generate the offline Town Observatory, or independently replay its package."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis.inspection_save import InspectionError
from src.analysis.town_showcase import build_package, verify_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path, help='new directory for the public demonstration package')
    mode.add_argument('--verify', type=Path, help='existing package to check with independent simulation and resume')
    args = parser.parse_args()
    output = args.output.resolve() if args.output else None
    source = args.verify.resolve() if args.verify else None
    os.chdir(ROOT)
    try:
        result = build_package(output) if output else verify_package(source)
    except (InspectionError, subprocess.TimeoutExpired, OSError, ValueError, KeyError, TypeError):
        print('Showcase failed: invalid input, output, evidence, or bounded evaluator failure. '
              'Use a new output directory and the supported repository revision.', file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
