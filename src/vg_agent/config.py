"""Generated runtime constants from MODEL_CONFIG.md."""

SPEC_DIGEST = "2e4178571694de33d19b4745b6c7701d2e916169e0b05e3d637fb42bb0eecacb"

PARENT_MODEL_ID = "openrouter/google/gemini-2.5-flash"
GRILLING_MODEL_ID = "openrouter/google/gemini-2.5-flash"
EXPLORER_MODEL_ID = "openrouter/google/gemini-2.5-flash"
CODER_MODEL_ID = "openrouter/google/gemini-2.5-flash"
REVIEWER_MODEL_ID = "openrouter/google/gemini-2.5-flash"
COMPACTOR_MODEL_ID = "openrouter/google/gemini-2.5-flash"

SUBAGENT_MODEL_IDS = {
    "grilling": GRILLING_MODEL_ID,
    "explorer": EXPLORER_MODEL_ID,
    "coder": CODER_MODEL_ID,
    "reviewer": REVIEWER_MODEL_ID,
}

PRICING_USD_PER_MTOK = {
    "openrouter/google/gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
    "openrouter/google/gemini-2.5-flash": {"input": 0.10, "output": 0.40},
    "openrouter/google/gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
    "openrouter/anthropic/claude-haiku-4.5": {"input": 1.00, "output": 5.00},
    "openrouter/anthropic/claude-sonnet-4.6": {"input": 3.00, "output": 15.00},
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": {"input": 0.07, "output": 0.27},
    "openrouter/deepseek/deepseek-v4-flash": {"input": 0.0983, "output": 0.1966},
}
UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK = {"input": 30.00, "output": 120.00}
EXPENSIVE_OPENROUTER_PROVIDER_SLUGS = ('alibaba', 'morph', 'parasail/fp8')

CONTEXT_WINDOW_TOKENS = {
    "openrouter/google/gemini-2.0-flash-001": 1000000,
    "openrouter/google/gemini-2.5-flash": 1048576,
    "openrouter/google/gemini-2.5-flash-lite": 1048576,
    "openrouter/anthropic/claude-haiku-4.5": 200000,
    "openrouter/anthropic/claude-sonnet-4.6": 200000,
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": 160000,
    "openrouter/deepseek/deepseek-v4-flash": 1048576,
}
AUTO_COMPACT_FRACTION = {
    "openrouter/google/gemini-2.0-flash-001": 0.80,
    "openrouter/google/gemini-2.5-flash": 0.80,
    "openrouter/google/gemini-2.5-flash-lite": 0.80,
    "openrouter/anthropic/claude-haiku-4.5": 0.80,
    "openrouter/anthropic/claude-sonnet-4.6": 0.80,
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": 0.80,
    "openrouter/deepseek/deepseek-v4-flash": 0.80,
}
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_COMPACT_FRACTION = 0.80
COMPACT_KEEP_RECENT_TURNS = 4
COMPACTOR_MAX_OUTPUT_TOKENS = 400
COMPACTOR_MAX_INPUT_CHARS = 120_000
COMPACTOR_MAX_SUMMARY_TOKENS = 300

MAX_PARENT_STEPS = 15
MAX_SUBAGENT_STEPS = 8
MAX_SUBAGENT_DEPTH = 1
MAX_CONCURRENT_SUBAGENTS = 2
MAX_PARALLEL_SUBAGENTS = 4
SUBAGENT_TYPES = ("grilling", "explorer", "coder", "reviewer")
MAX_TOKENS_PER_RUN = 80_000
MAX_USD_PER_RUN = 0.50
MAX_USD_PER_DAY = 5.00
WARN_USD_FRACTION = 0.8
WARN_TOKEN_FRACTION = 0.8
WARN_STEP_FRACTION = 0.8
WALL_CLOCK_TIMEOUT = 120
TOOL_TIMEOUT = 30
K_COMPACT = 4000

OPENROUTER_ENDPOINT_HOST = "openrouter.ai"
MAX_TOOL_RESULT_BYTES = 1_048_576
DAILY_SPEND_FILE = ".vg_daily_spend.json"
APPROVALS_FILE = ".vg_approvals.json"
REQUIRE_APPROVAL_DEFAULT = "off"
STEP_EXTEND_PROMPT_ON_LAST_STEP = True
SQLITE_TRACE_DB = "traces/vg_agent.sqlite3"
