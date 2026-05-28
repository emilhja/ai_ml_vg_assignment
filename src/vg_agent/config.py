"""Generated runtime constants from MODEL_CONFIG.md."""

SPEC_DIGEST = "22fb5187a6358ff2dc348d884fc8978829924711cb44fb9b731701a745437dd0"

PARENT_MODEL_ID = "openrouter/anthropic/claude-haiku-4.5"
EXPLORER_MODEL_ID = "openrouter/anthropic/claude-haiku-4.5"
COMPACTOR_MODEL_ID = "openrouter/anthropic/claude-haiku-4.5"

PRICING_USD_PER_MTOK = {
    "openrouter/anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    "openrouter/anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
}
UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK = {"input": 30.00, "output": 120.00}

MAX_PARENT_STEPS = 15
MAX_SUBAGENT_STEPS = 8
MAX_SUBAGENT_DEPTH = 1
MAX_CONCURRENT_SUBAGENTS = 2
MAX_TOKENS_PER_RUN = 80_000
MAX_USD_PER_RUN = 0.50
MAX_USD_PER_DAY = 5.00
WALL_CLOCK_TIMEOUT = 120
TOOL_TIMEOUT = 30
K_COMPACT = 4000

OPENROUTER_ENDPOINT_HOST = "openrouter.ai"
MAX_TOOL_RESULT_BYTES = 1_048_576
DAILY_SPEND_FILE = ".vg_daily_spend.json"
APPROVALS_FILE = ".vg_approvals.json"
REQUIRE_APPROVAL_DEFAULT = "off"
