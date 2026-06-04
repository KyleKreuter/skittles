"""The simulation orchestrator: deal skittles, run the rounds, score, report."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from skittles.agents.base import Agent
from skittles.agents.cost import CostTracker
from skittles.agents.heuristic_agent import HeuristicAgent
from skittles.agents.tools import ToolContext
from skittles.domain.colors import COLOR_ORDER
from skittles.domain.inventory import Inventory
from skittles.market.exchange import Exchange
from skittles.obs.events import EventLogger
from skittles.obs.report import build_report, write_report
from skittles.sim.config import AgentConfig, ExperimentConfig
from skittles.sim.scoring import ScoreBoard, score_run

RoundCallback = Callable[[int, dict], None]


@dataclass
class RunResult:
    run_dir: Path
    scoreboard: ScoreBoard
    report: dict
    total_trades: int
    total_cost_usd: float

    @property
    def winner(self) -> str:
        return self.scoreboard.winner.agent_id


class SimulationEngine:
    def __init__(self, config: ExperimentConfig) -> None:
        self.config = config

    def run(self, round_callback: RoundCallback | None = None) -> RunResult:
        cfg = self.config
        dist_rng = random.Random(cfg.seed)
        order_rng = random.Random(f"{cfg.seed}:turn-order")

        inventories = {
            a.id: Inventory.random(cfg.initial_skittles, dist_rng) for a in cfg.agents
        }

        run_dir = Path(cfg.output_dir) / datetime.now().strftime("%Y%m%d-%H%M%S")
        started_at = datetime.now().isoformat(timespec="seconds")

        with EventLogger(run_dir) as logger:
            exchange = Exchange(
                inventories,
                event_sink=logger.exchange_sink,
                fee_rate=cfg.fee_rate,
            )
            tracker = CostTracker(cfg.max_cost_usd)
            agents = [self._build_agent(a, cfg, tracker) for a in cfg.agents]

            logger.log("run_started", {
                "seed": cfg.seed,
                "rounds": cfg.rounds,
                "agents": [a.id for a in cfg.agents],
            })
            for agent_id, inv in inventories.items():
                logger.log("initial_inventory", {"agent_id": agent_id, **inv.snapshot()})

            snapshots: list[dict] = []
            self._snapshot(exchange, agents, 0, snapshots, logger, trades_before=0)

            for r in range(1, cfg.rounds + 1):
                logger.current_round = r
                turn_order = agents[:]
                order_rng.shuffle(turn_order)
                trades_before = len(exchange.trades)

                for agent in turn_order:
                    ctx = ToolContext(
                        exchange,
                        agent.agent_id,
                        round_index=r,
                        rounds_total=cfg.rounds,
                        market_depth=cfg.market_depth,
                    )
                    try:
                        agent.act(ctx)
                    except Exception as exc:  # never let one agent crash the run
                        logger.log("agent_error", {
                            "agent_id": agent.agent_id,
                            "error": f"{type(exc).__name__}: {exc}",
                        })

                snap = self._snapshot(exchange, agents, r, snapshots, logger, trades_before)
                if round_callback is not None:
                    round_callback(r, snap)

            # Settle: cancel every resting order so all skittles are available.
            for agent in agents:
                exchange.cancel_all(agent.agent_id)
            logger.current_round = cfg.rounds
            self._snapshot(exchange, agents, cfg.rounds, snapshots, logger,
                           trades_before=len(exchange.trades), label="final",
                           append=False)

            scoreboard = score_run(exchange)
            finished_at = datetime.now().isoformat(timespec="seconds")

            report = build_report(
                config=cfg,
                scoreboard=scoreboard,
                exchange=exchange,
                agents=agents,
                snapshots=snapshots,
                started_at=started_at,
                finished_at=finished_at,
            )
            write_report(run_dir, report)
            logger.log("run_finished", {
                "winner": scoreboard.winner.agent_id,
                "total_trades": len(exchange.trades),
                "total_cost_usd": report["total_cost_usd"],
                "fees_collected_total": report["fees_collected_total"],
            })

        return RunResult(
            run_dir=run_dir,
            scoreboard=scoreboard,
            report=report,
            total_trades=len(exchange.trades),
            total_cost_usd=report["total_cost_usd"],
        )

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _build_agent(cfg: AgentConfig, exp: ExperimentConfig, tracker: CostTracker) -> Agent:
        if cfg.type == "heuristic":
            return HeuristicAgent(cfg.id, random.Random(f"{exp.seed}:{cfg.id}"))
        # Imported lazily so heuristic-only runs do not require litellm.
        from skittles.agents.llm_agent import LLMAgent

        return LLMAgent(cfg, exp, tracker)

    @staticmethod
    def _snapshot(
        exchange: Exchange,
        agents: list[Agent],
        round_index: int,
        snapshots: list[dict],
        logger: EventLogger,
        trades_before: int,
        label: str | None = None,
        append: bool = True,
    ) -> dict:
        agents_data = {}
        for agent in agents:
            inv = exchange.inventories[agent.agent_id]
            color, count = inv.max_color()
            agents_data[agent.agent_id] = {
                "available": {c.value: inv.available[c] for c in COLOR_ORDER},
                "reserved_total": sum(inv.reserved.values()),
                "leading_color": color.value,
                "leading_count": count,
                "grand_total": inv.grand_total(),
                "open_orders": len(exchange.open_orders(agent.agent_id)),
            }
        snap = {
            "round": round_index,
            "label": label,
            "round_trades": len(exchange.trades) - trades_before,
            "total_trades": len(exchange.trades),
            "agents": agents_data,
        }
        if append:
            snapshots.append(snap)
        logger.snapshot(snap)
        return snap
