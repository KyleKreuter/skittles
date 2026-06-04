"""Command-line entry point: ``python -m skittles.cli run --config ...``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skittles.sim.config import load_config
from skittles.sim.engine import RunResult, SimulationEngine


def _load_env() -> None:
    """Load a local .env so provider API keys reach LiteLLM via os.environ."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _print(msg: str) -> None:
    try:
        from rich import print as rprint

        rprint(msg)
    except ImportError:
        # Strip simple rich markup for plain terminals.
        import re

        print(re.sub(r"\[/?[a-z0-9 ._-]*\]", "", msg))


def cmd_run(args: argparse.Namespace) -> int:
    _load_env()
    config = load_config(args.config)

    _print(f"[bold]Skittles Exchange[/bold] — {len(config.agents)} agents, "
           f"{config.rounds} rounds, seed {config.seed}")
    for a in config.agents:
        label = a.litellm_model if a.type == "llm" else "heuristic baseline"
        _print(f"  • [cyan]{a.id}[/cyan] ({label})")

    def on_round(r: int, snap: dict) -> None:
        leaders = ", ".join(
            f"{aid}:{d['leading_count']}{d['leading_color'][0]}"
            for aid, d in snap["agents"].items()
        )
        _print(f"  round [bold]{r:>3}[/bold]/{config.rounds}  "
               f"trades={snap['round_trades']:<3}  {leaders}")

    engine = SimulationEngine(config)
    result: RunResult = engine.run(round_callback=on_round if args.verbose else None)

    _print_summary(result)
    _print(f"\nArtifacts: [green]{result.run_dir}[/green]")
    return 0


def _print_summary(result: RunResult) -> None:
    _print("\n[bold]Result[/bold]")
    _print(f"  Winner: [bold green]{result.winner}[/bold green]")
    _print(f"  Trades: {result.total_trades}   Cost: ${result.total_cost_usd:.4f}")
    _print("  Final standings:")
    for i, score in enumerate(result.scoreboard.ranking, start=1):
        _print(f"    {i}. [cyan]{score.agent_id}[/cyan] — "
               f"{score.leading_count} × {score.leading_color.value} "
               f"(total {score.grand_total})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skittles", description="Skittles trading experiment")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run an experiment from a config file")
    run.add_argument("--config", "-c", default="config/experiment.yaml",
                     help="path to the experiment YAML (default: config/experiment.yaml)")
    run.add_argument("--verbose", "-v", action="store_true", help="print per-round progress")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not Path(args.config).exists():
        _print(f"[red]config not found:[/red] {args.config}")
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
