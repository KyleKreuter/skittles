#!/usr/bin/env python3
"""Plot the results of a run directory.

Usage:
    python scripts/analyze.py runs/<timestamp>

Produces, inside the run directory:
    leading_over_time.png  — each agent's leading single-color count per round
    trades_per_round.png   — trading activity over the run
    cost_per_agent.png     — API cost per agent (LLM agents only)

Requires the optional analysis extras: pip install -e ".[analysis]"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


def load_snapshots(run_dir: Path) -> pd.DataFrame:
    rows = []
    with (run_dir / "snapshots.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            snap = json.loads(line)
            if snap.get("label") == "final":
                continue
            for agent_id, data in snap["agents"].items():
                rows.append({
                    "round": snap["round"],
                    "agent": agent_id,
                    "leading_count": data["leading_count"],
                    "leading_color": data["leading_color"],
                    "round_trades": snap["round_trades"],
                })
    return pd.DataFrame(rows)


def plot_leading_over_time(df: pd.DataFrame, run_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5))
    for agent, sub in df.groupby("agent"):
        sub = sub.sort_values("round")
        ax.plot(sub["round"], sub["leading_count"], marker="o", ms=3, label=agent)
    ax.set_xlabel("round")
    ax.set_ylabel("leading single-color count")
    ax.set_title("Leading color count over time")
    ax.legend()
    ax.grid(alpha=0.3)
    out = run_dir / "leading_over_time.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_trades_per_round(df: pd.DataFrame, run_dir: Path) -> Path:
    per_round = df.drop_duplicates("round").sort_values("round")
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.bar(per_round["round"], per_round["round_trades"])
    ax.set_xlabel("round")
    ax.set_ylabel("trades")
    ax.set_title("Trades per round")
    ax.grid(alpha=0.3, axis="y")
    out = run_dir / "trades_per_round.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def plot_cost_per_agent(run_dir: Path) -> Path | None:
    report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    agents = [a for a in report["agents"] if a.get("cost_usd")]
    if not agents:
        return None
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([a["agent_id"] for a in agents], [a["cost_usd"] for a in agents])
    ax.set_ylabel("USD")
    ax.set_title("API cost per agent")
    ax.grid(alpha=0.3, axis="y")
    out = run_dir / "cost_per_agent.png"
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    run_dir = Path(argv[1])
    if not (run_dir / "snapshots.jsonl").exists():
        print(f"no snapshots.jsonl in {run_dir}")
        return 2

    df = load_snapshots(run_dir)
    outputs = [
        plot_leading_over_time(df, run_dir),
        plot_trades_per_round(df, run_dir),
        plot_cost_per_agent(run_dir),
    ]
    for out in outputs:
        if out:
            print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
