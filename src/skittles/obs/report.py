"""Build and persist the end-of-run research report (``report.json``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from skittles.market.exchange import Exchange
from skittles.sim.eval import evaluate
from skittles.sim.scoring import ScoreBoard

if TYPE_CHECKING:  # avoid import cycles at runtime
    from skittles.agents.base import Agent
    from skittles.sim.config import ExperimentConfig
    from skittles.social.forum import Forum


def build_report(
    *,
    config: "ExperimentConfig",
    scoreboard: ScoreBoard,
    exchange: Exchange,
    agents: list["Agent"],
    snapshots: list[dict],
    started_at: str,
    finished_at: str,
    forum: "Forum | None" = None,
) -> dict:
    """Assemble the structured run report as a plain dict."""
    agents_by_id = {a.agent_id: a for a in agents}
    cfg_by_id = {a.id: a for a in config.agents}
    broadcasts = forum.count_by_agent() if forum else {}

    per_agent = []
    for score in scoreboard.ranking:
        agent = agents_by_id.get(score.agent_id)
        cfg = cfg_by_id.get(score.agent_id)
        per_agent.append(
            {
                "agent_id": score.agent_id,
                "type": cfg.type if cfg else "unknown",
                "model": (cfg.litellm_model if cfg and cfg.type == "llm" else None),
                "leading_color": score.leading_color.value,
                "leading_count": score.leading_count,
                "grand_total": score.grand_total,
                "cost_usd": round(agent.cost_usd, 6) if agent else 0.0,
                "broadcasts": broadcasts.get(score.agent_id, 0),
                "trajectory": _trajectory(snapshots, score.agent_id),
                "notes": agent.notes if agent else [],
            }
        )

    # Log score in [0,1] vs the baseline (ground zero); also fold it per agent.
    evaluation = evaluate(per_agent, initial_skittles=config.initial_skittles)
    score_by_id = {s["agent_id"]: s["log_score"] for s in evaluation["scores"]}
    for a in per_agent:
        a["log_score"] = score_by_id.get(a["agent_id"], 0.0)

    total_cost = round(sum(a.cost_usd for a in agents), 6)
    fees = {c.value: n for c, n in exchange.fees_collected.items()}

    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "config": {
            "rounds": config.rounds,
            "seed": config.seed,
            "initial_skittles": config.initial_skittles,
            "fee_rate": config.fee_rate,
            "max_tool_calls_per_turn": config.max_tool_calls_per_turn,
            "max_cost_usd": config.max_cost_usd,
            "num_agents": len(config.agents),
        },
        "winner": scoreboard.winner.agent_id,
        "rounds_completed": snapshots[-1]["round"] if snapshots else 0,
        "total_trades": len(exchange.trades),
        "total_cost_usd": total_cost,
        "fees_collected": fees,
        "fees_collected_total": sum(fees.values()),
        "total_broadcasts": len(forum.posts) if forum else 0,
        "forum_transcript": [p.to_dict() for p in forum.posts] if forum else [],
        "evaluation": evaluation,
        "agents": per_agent,
    }


def _trajectory(snapshots: list[dict], agent_id: str) -> list[dict]:
    """Per-round leading-color count for one agent, for plotting."""
    points = []
    for snap in snapshots:
        agent_snap = snap.get("agents", {}).get(agent_id)
        if agent_snap is None:
            continue
        points.append(
            {
                "round": snap["round"],
                "leading_color": agent_snap["leading_color"],
                "leading_count": agent_snap["leading_count"],
            }
        )
    return points


def write_report(run_dir: str | Path, report: dict) -> Path:
    path = Path(run_dir) / "report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
