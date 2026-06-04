"""LiteLLM-backed trading agent.

One turn = a fresh tool-calling loop seeded with a system prompt and a compact
observation of the current state. We deliberately do NOT carry the full message
history across rounds: the world (inventory + order book) is the persistent
state the model re-observes each turn, which keeps token cost bounded over many
rounds. A short rationale the model emits is captured for the research report.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from skittles.agents.base import Agent
from skittles.agents.cost import CostTracker
from skittles.agents.prompts import build_observation, system_prompt
from skittles.agents.tools import ToolContext, dispatch, tool_specs
from skittles.sim.config import AgentConfig, ExperimentConfig

CompletionFn = Callable[..., Any]


class LLMAgent(Agent):
    def __init__(
        self,
        cfg: AgentConfig,
        exp: ExperimentConfig,
        tracker: CostTracker,
        completion_fn: CompletionFn | None = None,
    ) -> None:
        super().__init__(cfg.id)
        self.cfg = cfg
        self.exp = exp
        self.tracker = tracker
        self._completion_fn = completion_fn
        self._cost = 0.0
        self._notes: list[str] = []
        self._tools = tool_specs(exp.forum_enabled)
        self._system = system_prompt(exp.initial_skittles, exp.forum_enabled)

    @property
    def cost_usd(self) -> float:
        return self._cost

    @property
    def notes(self) -> list[str]:
        return self._notes

    def act(self, ctx: ToolContext) -> None:
        if self.tracker.exhausted():
            self._notes.append(f"round {ctx.round_index}: budget exhausted, skipped")
            return

        messages: list[dict] = [
            {"role": "system", "content": self._system},
            {"role": "user", "content": build_observation(ctx)},
        ]

        for _ in range(self.exp.max_tool_calls_per_turn):
            if self.tracker.exhausted():
                break
            try:
                response = self._complete(messages)
            except Exception as exc:  # API/network hiccup: end turn gracefully
                self._notes.append(f"round {ctx.round_index}: API error {exc}")
                break

            self._cost += _response_cost(response)
            self.tracker.add(_response_cost(response))

            message = response.choices[0].message
            messages.append(_assistant_dict(message))

            content = (getattr(message, "content", None) or "").strip()
            if content:
                self._notes.append(f"round {ctx.round_index}: {content}")

            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                break  # model produced no action; treat as end of turn

            for call in tool_calls:
                name = call.function.name
                args = _parse_args(call.function.arguments)
                result = dispatch(ctx, name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            if ctx.done:
                break

    # --- LLM call --------------------------------------------------------

    def _complete(self, messages: list[dict]) -> Any:
        fn = self._completion_fn
        if fn is None:
            import litellm  # imported lazily so tests can inject a fake

            fn = litellm.completion
        return fn(
            model=self.cfg.litellm_model,
            messages=messages,
            tools=self._tools,
            tool_choice="auto",
            temperature=self.cfg.temperature,
        )


def _response_cost(response: Any) -> float:
    """Best-effort USD cost of a single completion via LiteLLM metadata."""
    hidden = getattr(response, "_hidden_params", None) or {}
    cost = hidden.get("response_cost")
    if cost is not None:
        return float(cost)
    try:
        import litellm

        return float(litellm.completion_cost(completion_response=response) or 0.0)
    except Exception:
        return 0.0


def _assistant_dict(message: Any) -> dict:
    """Serialize an assistant message (with optional tool_calls) for the next call."""
    if hasattr(message, "model_dump"):
        data = message.model_dump(exclude_none=True)
        data["role"] = "assistant"
        return data
    out: dict = {"role": "assistant", "content": getattr(message, "content", None)}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in tool_calls
        ]
    return out


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
