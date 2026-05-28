"""Generated runtime constants from MODEL_CONFIG.md."""

SPEC_DIGEST = "2a91e807518775e7ee4dda52972006e8cce9fa190bc94aa6f6296092fd3666a8"

PARENT_MODEL_ID = "openrouter/google/gemini-2.0-flash-001"
EXPLORER_MODEL_ID = "openrouter/google/gemini-2.0-flash-001"
COMPACTOR_MODEL_ID = "openrouter/google/gemini-2.0-flash-001"

PRICING_USD_PER_MTOK = {
    "openrouter/google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
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
SQLITE_TRACE_DB = "traces/vg_agent.sqlite3"
