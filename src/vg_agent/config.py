"""Generated runtime constants from MODEL_CONFIG.md."""

SPEC_DIGEST = "90e8c0739d3c3161ad83a074c3172f07d3217d6efb7b6acbeb17abe2405e6076"

PARENT_MODEL_ID = "openrouter/google/gemini-2.5-flash"
GRILLING_MODEL_ID = "openrouter/google/gemini-2.5-flash"
EXPLORER_MODEL_ID = "openrouter/google/gemini-2.5-flash"
CODER_MODEL_ID = "openrouter/anthropic/claude-haiku-4.5"
REVIEWER_MODEL_ID = "openrouter/google/gemini-2.5-flash"
COMPACTOR_MODEL_ID = "openrouter/google/gemini-2.5-flash"

SUBAGENT_MODEL_IDS = {
    "grilling": GRILLING_MODEL_ID,
    "explorer": EXPLORER_MODEL_ID,
    "coder": CODER_MODEL_ID,
    "reviewer": REVIEWER_MODEL_ID,
}

# Per-model catalog: each model id is listed once with its pricing
# (USD/Mtok), context window, and auto-compact fraction. The public dicts
# below are derived from it so adding a model means one entry here, not edits
# to three parallel dicts. They stay plain dicts so runtime_settings and tests
# can still mutate them in place.
_MODELS: dict[str, dict] = {
    "openrouter/google/gemini-2.0-flash-001": {
        "pricing": {"input": 0.10, "output": 0.40},
        "context_window": 1000000,
        "compact_fraction": 0.80,
    },
    "openrouter/google/gemini-2.5-flash": {
        "pricing": {"input": 0.10, "output": 0.40},
        "context_window": 1048576,
        "compact_fraction": 0.80,
    },
    "openrouter/google/gemini-2.5-flash-lite": {
        "pricing": {"input": 0.10, "output": 0.40},
        "context_window": 1048576,
        "compact_fraction": 0.80,
    },
    "openrouter/anthropic/claude-haiku-4.5": {
        "pricing": {"input": 1.00, "output": 5.00},
        "context_window": 200000,
        "compact_fraction": 0.80,
    },
    "openrouter/anthropic/claude-sonnet-4.6": {
        "pricing": {"input": 3.00, "output": 15.00},
        "context_window": 200000,
        "compact_fraction": 0.80,
    },
    "openrouter/qwen/qwen3-coder-30b-a3b-instruct": {
        "pricing": {"input": 0.07, "output": 0.27},
        "context_window": 160000,
        "compact_fraction": 0.80,
    },
    "openrouter/deepseek/deepseek-v4-flash": {
        "pricing": {"input": 0.0983, "output": 0.1966},
        "context_window": 1048576,
        "compact_fraction": 0.80,
    },
}

PRICING_USD_PER_MTOK = {mid: spec["pricing"] for mid, spec in _MODELS.items()}
CONTEXT_WINDOW_TOKENS = {mid: spec["context_window"] for mid, spec in _MODELS.items()}
AUTO_COMPACT_FRACTION = {mid: spec["compact_fraction"] for mid, spec in _MODELS.items()}
UNKNOWN_MODEL_ESTIMATE_USD_PER_MTOK = {"input": 30.00, "output": 120.00}
EXPENSIVE_OPENROUTER_PROVIDER_SLUGS = ('alibaba', 'morph', 'parasail/fp8')
DEFAULT_CONTEXT_WINDOW = 128_000
DEFAULT_COMPACT_FRACTION = 0.80
COMPACT_KEEP_RECENT_TURNS = 4
COMPACTOR_MAX_OUTPUT_TOKENS = 400
COMPACTOR_MAX_INPUT_CHARS = 120_000
COMPACTOR_MAX_SUMMARY_TOKENS = 300

MAX_PARENT_STEPS = 15
FINAL_STEP_RESERVE = 1
MAX_PARALLEL_CODER_RETRIES_PER_CALL = 2
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
PARENT_MAX_OUTPUT_TOKENS = 4096

OPENROUTER_ENDPOINT_HOST = "openrouter.ai"
MAX_TOOL_RESULT_BYTES = 1_048_576
DAILY_SPEND_FILE = ".vg_daily_spend.json"
APPROVALS_FILE = ".vg_approvals.json"
REQUIRE_APPROVAL_DEFAULT = "off"
STEP_EXTEND_PROMPT_ON_LAST_STEP = True
SQLITE_TRACE_DB = "traces/vg_agent.sqlite3"
