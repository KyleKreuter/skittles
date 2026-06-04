#!/usr/bin/env python3
"""Log-score evaluation of a run, with the baseline as ground zero.

Usage:
    python scripts/eval.py runs/<timestamp> [--ceiling N]

Recomputes the metric from report.json, so it works on older runs too.
Score 0 = baseline level (ground zero), 1 = perfect single-color hoard.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a plain script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from skittles.sim.eval import evaluate  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Log-score eval of a run")
    parser.add_argument("run_dir", help="path to a runs/<timestamp> directory")
    parser.add_argument("--ceiling", type=int, default=None,
                        help="score-1 ceiling (default: initial_skittles from the run)")
    args = parser.parse_args(argv[1:])

    report_path = Path(args.run_dir) / "report.json"
    if not report_path.exists():
        print(f"no report.json in {args.run_dir}")
        return 2
    report = json.loads(report_path.read_text(encoding="utf-8"))

    initial = report.get("config", {}).get("initial_skittles", 100)
    result = evaluate(report["agents"], initial_skittles=initial, ceiling=args.ceiling)

    print(f"Ground zero (baseline '{result['baseline_id']}'): "
          f"{result['floor']} | ceiling: {result['ceiling']}")
    print(f"{'rank':<5}{'agent':14}{'model':22}{'lead':>5}{'log_score':>11}")
    for i, s in enumerate(result["scores"], 1):
        model = s.get("model") or s.get("type") or ""
        bar = "█" * round(s["log_score"] * 20)
        print(f"{i:<5}{s['agent_id']:14}{model:22}{s['leading_count']:>5}"
              f"{s['log_score']:>11.3f}  {bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
