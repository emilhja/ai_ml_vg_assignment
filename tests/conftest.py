"""Reset vg_agent.config after dashboard startup or runtime_settings tests."""

from __future__ import annotations

import pytest

from vg_agent import config

_CONFIG_KEYS = (
    "PARENT_MODEL_ID",
    "GRILLING_MODEL_ID",
    "EXPLORER_MODEL_ID",
    "CODER_MODEL_ID",
    "REVIEWER_MODEL_ID",
    "COMPACTOR_MODEL_ID",
    "MAX_USD_PER_RUN",
    "MAX_TOKENS_PER_RUN",
    "K_COMPACT",
    "REQUIRE_APPROVAL_DEFAULT",
)

_SNAPSHOT: dict[str, object] = {key: getattr(config, key) for key in _CONFIG_KEYS}
_SNAPSHOT["SUBAGENT_MODEL_IDS"] = dict(config.SUBAGENT_MODEL_IDS)


def _restore_config_defaults() -> None:
    for key, value in _SNAPSHOT.items():
        if key == "SUBAGENT_MODEL_IDS":
            config.SUBAGENT_MODEL_IDS.clear()
            config.SUBAGENT_MODEL_IDS.update(value)  # type: ignore[arg-type]
        else:
            setattr(config, key, value)


@pytest.fixture(autouse=True)
def _isolate_mutable_config() -> None:
    _restore_config_defaults()
    yield
    _restore_config_defaults()
