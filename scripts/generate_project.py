from __future__ import annotations

import argparse
import hashlib
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_INPUTS = [
    ROOT / "specs" / "00_overview.md",
    ROOT / "specs" / "10_main_agent.md",
    ROOT / "specs" / "11_subagent_explorer.md",
    ROOT / "specs" / "20_tools.md",
    ROOT / "specs" / "30_runtime_governance.md",
    ROOT / "specs" / "40_demo_and_eval.md",
    ROOT / "PROMPTS.md",
    ROOT / "MODEL_CONFIG.md",
    ROOT / "CONTEXT_WINDOWS.md",
]


def read_config() -> dict[str, str]:
    text = (ROOT / "MODEL_CONFIG.md").read_text(encoding="utf-8")
    keys = [
        "PARENT_MODEL_ID",
        "GRILLING_MODEL_ID",
        "EXPLORER_MODEL_ID",
        "CODER_MODEL_ID",
        "REVIEWER_MODEL_ID",
        "COMPACTOR_MODEL_ID",
        "GEMINI_2_0_FLASH_INPUT_PER_MTOK",
        "GEMINI_2_0_FLASH_OUTPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_INPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_OUTPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_LITE_INPUT_PER_MTOK",
        "GEMINI_2_5_FLASH_LITE_OUTPUT_PER_MTOK",
        "CLAUDE_SONNET_4_6_INPUT_PER_MTOK",
        "CLAUDE_SONNET_4_6_OUTPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_INPUT_PER_MTOK",
        "CLAUDE_HAIKU_4_5_OUTPUT_PER_MTOK",
        "QWEN3_CODER_30B_INPUT_PER_MTOK",
        "QWEN3_CODER_30B_OUTPUT_PER_MTOK",
        "DEEPSEEK_V4_FLASH_INPUT_PER_MTOK",
        "DEEPSEEK_V4_FLASH_OUTPUT_PER_MTOK",
        "EXPENSIVE_OPENROUTER_PROVIDER_SLUGS",
        "UNKNOWN_MODEL_INPUT_ESTIMATE_PER_MTOK",
        "UNKNOWN_MODEL_OUTPUT_ESTIMATE_PER_MTOK",
        "OPENROUTER_ENDPOINT_HOST",
    ]
    values: dict[str, str] = {}
    for key in keys:
        match = re.search(rf"^{key}:\s*([^\n]+)$", text, flags=re.MULTILINE)
        if not match:
            raise SystemExit(f"missing {key} in MODEL_CONFIG.md")
        values[key] = match.group(1).strip()
    return values


def read_context_windows() -> dict[str, str]:
    text = (ROOT / "CONTEXT_WINDOWS.md").read_text(encoding="utf-8")
    keys = [
        "GEMINI_2_0_FLASH_CONTEXT_WINDOW",
        "GEMINI_2_0_FLASH_COMPACT_FRACTION",
        "GEMINI_2_5_FLASH_CONTEXT_WINDOW",
        "GEMINI_2_5_FLASH_COMPACT_FRACTION",
        "GEMINI_2_5_FLASH_LITE_CONTEXT_WINDOW",
        "GEMINI_2_5_FLASH_LITE_COMPACT_FRACTION",
        "CLAUDE_HAIKU_4_5_CONTEXT_WINDOW",
        "CLAUDE_HAIKU_4_5_COMPACT_FRACTION",
        "CLAUDE_SONNET_4_6_CONTEXT_WINDOW",
        "CLAUDE_SONNET_4_6_COMPACT_FRACTION",
        "QWEN3_CODER_30B_CONTEXT_WINDOW",
        "QWEN3_CODER_30B_COMPACT_FRACTION",
        "DEEPSEEK_V4_FLASH_CONTEXT_WINDOW",
        "DEEPSEEK_V4_FLASH_COMPACT_FRACTION",
    ]
    values: dict[str, str] = {}
    for key in keys:
        match = re.search(rf"^{key}:\s*([^\n]+)$", text, flags=re.MULTILINE)
        if not match:
            raise SystemExit(f"missing {key} in CONTEXT_WINDOWS.md")
        values[key] = match.group(1).strip()
    return values


def read_prompts() -> dict[str, str]:
    text = (ROOT / "PROMPTS.md").read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    section_titles = {
        "PARENT_SYSTEM_PROMPT": "## Parent system prompt",
        "GRILLING_SYSTEM_PROMPT": "## Grilling system prompt",
        "EXPLORER_SYSTEM_PROMPT": "## Explorer system prompt",
        "CODER_SYSTEM_PROMPT": "## Coder system prompt",
        "REVIEWER_SYSTEM_PROMPT": "## Reviewer system prompt",
        "COMPACTION_SYSTEM_PROMPT": "## Tool-result compaction prompt",
        "CONVERSATION_COMPACTION_SYSTEM_PROMPT": "## Conversation compaction prompt",
    }
    for key, header in section_titles.items():
        pattern = re.escape(header) + r"\s*\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, text, flags=re.DOTALL)
        if not match:
            raise SystemExit(f"missing section {header!r} in PROMPTS.md")
        body = match.group(1).strip()
        sections[key] = body
    return sections


def python_str_literal(value: str) -> str:
    """Render a Python string literal that round-trips through generator output."""
    return repr(value)


def spec_digest() -> str:
    h = hashlib.sha256()
    for path in SOURCE_INPUTS:
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


_RESIDUAL_PLACEHOLDER = re.compile(r"__[A-Z][A-Z0-9_]*__")


def render(text: str, digest: str, cfg: dict[str, str], prompts: dict[str, str]) -> str:
    for key, value in cfg.items():
        text = text.replace(f"__{key}__", value)
    for key, value in prompts.items():
        text = text.replace(f"__{key}_LITERAL__", python_str_literal(value))
    text = text.replace("__SPEC_DIGEST__", digest)
    # Fail loudly on a typo'd/unknown placeholder instead of silently emitting
    # broken runtime code. Python dunders are lowercase, so the uppercase
    # pattern only matches intended __PLACEHOLDER__ tokens.
    leftover = sorted(set(_RESIDUAL_PLACEHOLDER.findall(text)))
    if leftover:
        raise SystemExit("unsubstituted template placeholder(s): " + ", ".join(leftover))
    return text


TEMPLATE_DIR = ROOT / "scripts" / "templates"


def _load_generated_templates() -> dict[str, str]:
    """Load generated-module templates from scripts/templates/*.tmpl.

    Each ``<name>.tmpl`` provides the pre-render source for the generated file
    ``<name>``; templates still contain ``__PLACEHOLDER__`` tokens that
    :func:`render` substitutes. Stored as files (not inline strings) so the
    generated runtime is reviewable with normal Python tooling.
    """
    if not TEMPLATE_DIR.is_dir():
        raise SystemExit(f"missing template dir: {TEMPLATE_DIR}")
    files: dict[str, str] = {}
    for path in sorted(TEMPLATE_DIR.glob("*.tmpl")):
        files[path.name[: -len(".tmpl")]] = path.read_text(encoding="utf-8")
    if not files:
        raise SystemExit(f"no templates found in {TEMPLATE_DIR}")
    return files


GENERATED_FILES: dict[str, str] = _load_generated_templates()


EXTRA_SOURCE_GENERATED_FILES = ["sqlite_store.py", "chat_ui.py", "workspace_paths.py"]


def write_generated(src_dir: Path, digest: str, cfg: dict[str, str], prompts: dict[str, str], clean: bool) -> None:
    extra_files: dict[str, str] = {}
    source_dir = ROOT / "src" / "vg_agent"
    for rel_path in EXTRA_SOURCE_GENERATED_FILES:
        source_path = source_dir / rel_path
        if source_path.exists():
            extra_files[rel_path] = source_path.read_text(encoding="utf-8")
    if clean and src_dir.exists():
        shutil.rmtree(src_dir)
    src_dir.mkdir(parents=True, exist_ok=True)
    for rel_path, text in {**GENERATED_FILES, **extra_files}.items():
        path = src_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(text, digest, cfg, prompts), encoding="utf-8", newline="\n")


def write_fixture(fixture_dir: Path, clean: bool) -> None:
    if clean and fixture_dir.exists():
        shutil.rmtree(fixture_dir)
    import sys

    src_parent = str((ROOT / "src").resolve())
    if src_parent not in sys.path:
        sys.path.insert(0, src_parent)
    from vg_agent.demo_fixture import write_fixture as generated_write_fixture

    generated_write_fixture(fixture_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-dir", default=str(ROOT / "src" / "vg_agent"))
    parser.add_argument("--fixture-dir", default=str(ROOT / "fixtures" / "demo_repo"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--no-fixture", action="store_true")
    args = parser.parse_args()

    cfg = read_config()
    cfg.update(read_context_windows())
    slug_parts = [part.strip() for part in cfg["EXPENSIVE_OPENROUTER_PROVIDER_SLUGS"].split(",") if part.strip()]
    cfg["EXPENSIVE_OPENROUTER_PROVIDER_SLUGS_TUPLE"] = repr(tuple(slug_parts))
    prompts = read_prompts()
    digest = spec_digest()
    src_dir = Path(args.src_dir)
    write_generated(src_dir, digest, cfg, prompts, args.clean)
    if not args.no_fixture:
        write_fixture(Path(args.fixture_dir), args.clean)
    print(f"generated {src_dir} from specs digest {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
