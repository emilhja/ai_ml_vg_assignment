"""Generated budget guard."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config


class PricingUnavailable(RuntimeError):
    pass


@dataclass
class BudgetDecision:
    allowed: bool
    budget_reason: str | None = None
    details: dict[str, object] = field(default_factory=dict)


def _today_utc_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class DailySpendLedger:
    """UTC date-keyed persistent ledger under workspace root."""

    def __init__(self, root: Path | None) -> None:
        self.root = root
        self.path: Path | None = None
        self.data: dict[str, float] = {}
        self.fail_closed: bool = False
        if root is None:
            return
        self.path = Path(root) / config.DAILY_SPEND_FILE
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("ledger payload must be an object")
            self.data = {str(k): float(v) for k, v in payload.items()}
        except (OSError, ValueError, json.JSONDecodeError):
            self.data = {}
            self.fail_closed = True

    def today_spent(self) -> float:
        return float(self.data.get(_today_utc_key(), 0.0))

    def remaining_today(self) -> float:
        if self.fail_closed:
            return 0.0
        return max(0.0, config.MAX_USD_PER_DAY - self.today_spent())

    def add(self, cost: float) -> None:
        if self.path is None or self.fail_closed:
            return
        key = _today_utc_key()
        self.data[key] = self.today_spent() + float(cost)
        try:
            self.path.write_text(
                json.dumps(self.data, sort_keys=True),
                encoding="utf-8",
                newline="\n",
            )
        except OSError:
            pass


@dataclass
class BudgetGuard:
    max_steps: int = config.MAX_PARENT_STEPS
    max_tokens: int = config.MAX_TOKENS_PER_RUN
    max_usd: float = config.MAX_USD_PER_RUN
    daily_remaining_usd: float = config.MAX_USD_PER_DAY
    running_tokens: int = 0
    running_input_tokens: int = 0
    running_output_tokens: int = 0
    running_usd: float = 0.0
    step_count: int = 0
    last_tool_signature: tuple[str, str] | None = None
    repeat_count: int = 0
    ledger: DailySpendLedger | None = None
    per_agent_type_tokens: dict[str, int] = field(default_factory=dict)
    per_agent_type_input_tokens: dict[str, int] = field(default_factory=dict)
    per_agent_type_output_tokens: dict[str, int] = field(default_factory=dict)
    per_agent_type_model_calls: dict[str, int] = field(default_factory=dict)
    per_agent_type_usd: dict[str, float] = field(default_factory=dict)
    warned: set[str] = field(default_factory=set)
    wall_clock_extra_s: float = 0.0
    lock: object = field(default_factory=threading.RLock, compare=False, repr=False)

    @classmethod
    def for_workspace(cls, root: Path | None, **kwargs: object) -> "BudgetGuard":
        ledger = DailySpendLedger(root)
        kwargs.setdefault("daily_remaining_usd", ledger.remaining_today())
        kwargs["ledger"] = ledger
        return cls(**kwargs)  # type: ignore[arg-type]

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = config.PRICING_USD_PER_MTOK.get(model, config.UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK)
        return (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]

    def before_model_call(self, model: str, worst_input_tokens: int, worst_output_tokens: int) -> BudgetDecision:
        with self.lock:
            if self.step_count >= self.max_steps:
                return BudgetDecision(False, "step_cap", {"steps": self.step_count, "max_steps": self.max_steps})
            if self.running_tokens + worst_input_tokens + worst_output_tokens > self.max_tokens:
                return BudgetDecision(False, "token_cap", {"tokens": self.running_tokens, "max_tokens": self.max_tokens})
            worst_cost = self.estimate_cost(model, worst_input_tokens, worst_output_tokens)
            if self.running_usd + worst_cost > self.max_usd:
                return BudgetDecision(False, "usd_cap", {"running_usd": self.running_usd, "worst_next_usd": worst_cost})
            if self.running_usd + worst_cost > self.daily_remaining_usd:
                return BudgetDecision(False, "daily_cap", {"running_usd": self.running_usd, "daily_remaining_usd": self.daily_remaining_usd})
            return BudgetDecision(True)

    def record_model_call(self, model: str, input_tokens: int, output_tokens: int, cost_usd: float | None = None, agent_type: str = "parent") -> float:
        with self.lock:
            self.step_count += 1
            self.running_tokens += input_tokens + output_tokens
            self.running_input_tokens += input_tokens
            self.running_output_tokens += output_tokens
            if cost_usd is not None:
                cost = float(cost_usd)
            elif model in config.PRICING_USD_PER_MTOK:
                cost = self.estimate_cost(model, input_tokens, output_tokens)
            else:
                raise PricingUnavailable(
                    f"no local pricing for live model {model!r}; OpenRouter/LiteLLM must return explicit response cost"
                )
            self.running_usd += cost
            self.per_agent_type_tokens[agent_type] = self.per_agent_type_tokens.get(agent_type, 0) + input_tokens + output_tokens
            self.per_agent_type_input_tokens[agent_type] = self.per_agent_type_input_tokens.get(agent_type, 0) + input_tokens
            self.per_agent_type_output_tokens[agent_type] = self.per_agent_type_output_tokens.get(agent_type, 0) + output_tokens
            self.per_agent_type_model_calls[agent_type] = self.per_agent_type_model_calls.get(agent_type, 0) + 1
            self.per_agent_type_usd[agent_type] = self.per_agent_type_usd.get(agent_type, 0.0) + cost
            if self.ledger is not None:
                self.ledger.add(cost)
            return cost

    def pending_warnings(self) -> list[BudgetDecision]:
        """Return budget warnings whose threshold was newly crossed (once each).

        Soft warnings never abort; the hard caps remain the only termination triggers.
        """
        with self.lock:
            out: list[BudgetDecision] = []
            if "warn_usd" not in self.warned and self.max_usd > 0 and self.running_usd >= config.WARN_USD_FRACTION * self.max_usd:
                self.warned.add("warn_usd")
                out.append(BudgetDecision(True, "warn_usd", {"running_usd": self.running_usd, "max_usd": self.max_usd, "crossed_at_step": self.step_count}))
            if "warn_tokens" not in self.warned and self.max_tokens > 0 and self.running_tokens >= config.WARN_TOKEN_FRACTION * self.max_tokens:
                self.warned.add("warn_tokens")
                out.append(BudgetDecision(True, "warn_tokens", {"running_tokens": self.running_tokens, "max_tokens": self.max_tokens, "crossed_at_step": self.step_count}))
            if "warn_steps" not in self.warned and self.max_steps > 0 and self.step_count >= config.WARN_STEP_FRACTION * self.max_steps:
                self.warned.add("warn_steps")
                out.append(BudgetDecision(True, "warn_steps", {"step_count": self.step_count, "max_steps": self.max_steps, "crossed_at_step": self.step_count}))
            return out

    def record_tool_signature(self, tool: str, args_key: str) -> BudgetDecision:
        with self.lock:
            signature = (tool, args_key)
            if signature == self.last_tool_signature:
                self.repeat_count += 1
            else:
                self.last_tool_signature = signature
                self.repeat_count = 1
            if self.repeat_count >= 3:
                return BudgetDecision(False, "repetition_abort", {"tool": tool, "args_key": args_key, "repeat_count": self.repeat_count})
            return BudgetDecision(True)

    def extend_cap(self, reason: str, *, once: bool) -> None:
        """Raise a hard cap after interactive approval."""
        with self.lock:
            if reason == "step_cap":
                self.max_steps = (self.step_count + 1) if once else (self.max_steps + max(5, self.max_steps // 4))
            elif reason == "token_cap":
                bump = max(10_000, self.max_tokens // 4)
                self.max_tokens = (self.running_tokens + bump) if once else (self.max_tokens + bump)
            elif reason == "usd_cap":
                bump = max(0.05, self.max_usd * 0.25)
                self.max_usd = (self.running_usd + bump) if once else (self.max_usd + bump)
            elif reason == "daily_cap":
                bump = max(0.25, self.daily_remaining_usd * 0.25) if self.daily_remaining_usd > 0 else 0.5
                self.daily_remaining_usd += bump
            elif reason == "timeout":
                self.wall_clock_extra_s += 60.0 if once else float(config.WALL_CLOCK_TIMEOUT)
            elif reason == "repetition_abort":
                self.repeat_count = 0
                self.last_tool_signature = None
