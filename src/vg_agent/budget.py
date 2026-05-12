"""Generated budget guard."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import config


@dataclass
class BudgetDecision:
    allowed: bool
    budget_reason: str | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass
class BudgetGuard:
    max_steps: int = config.MAX_PARENT_STEPS
    max_tokens: int = config.MAX_TOKENS_PER_RUN
    max_usd: float = config.MAX_USD_PER_RUN
    daily_remaining_usd: float = config.MAX_USD_PER_DAY
    running_tokens: int = 0
    running_usd: float = 0.0
    step_count: int = 0
    last_tool_signature: tuple[str, str] | None = None
    repeat_count: int = 0

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        price = config.PRICING_USD_PER_MTOK[model]
        return (input_tokens / 1_000_000) * price["input"] + (output_tokens / 1_000_000) * price["output"]

    def before_model_call(self, model: str, worst_input_tokens: int, worst_output_tokens: int) -> BudgetDecision:
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

    def record_model_call(self, model: str, input_tokens: int, output_tokens: int) -> float:
        self.step_count += 1
        self.running_tokens += input_tokens + output_tokens
        cost = self.estimate_cost(model, input_tokens, output_tokens)
        self.running_usd += cost
        return cost

    def record_tool_signature(self, tool: str, args_key: str) -> BudgetDecision:
        signature = (tool, args_key)
        if signature == self.last_tool_signature:
            self.repeat_count += 1
        else:
            self.last_tool_signature = signature
            self.repeat_count = 1
        if self.repeat_count >= 3:
            return BudgetDecision(False, "repetition_abort", {"tool": tool, "args_key": args_key, "repeat_count": self.repeat_count})
        return BudgetDecision(True)
