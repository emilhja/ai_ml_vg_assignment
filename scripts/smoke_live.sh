#!/usr/bin/env bash
#
# Minimal live smoke test for vg_agent (bash port of scripts/smoke_live.ps1).
#
# Fires ONE tuned prompt per VG feature through the canonical Docker path,
# auto-verifies each run against its JSONL trace, and writes
# traces/smoke_report.md. This is a regression smoke check, not the full
# presentation in docs/demo/quick_demo.md. Use it after large changes or when
# swapping models: a green board means every hard gate and VG.1-VG.9 mechanism
# still fires.
#
# Each feature is a single headless `docker compose run --task ...` (no chat,
# no TTY, stdin pinned to /dev/null), so approvals/caps resolve
# deterministically regardless of the .env VG_APPROVAL_MODE:
#   --yes                      -> gated tool auto-approves, decision:"auto"
#   no --yes + EOF stdin        -> approval prompt reads EOF -> decision:"denied"
#   --max-usd 0.01              -> usd_cap abort, exit code 3
# Under VG_APPROVAL_MODE=writes, run_bash / spawn_subagents / edit_file are all
# gated, so the happy-path features (F1-F6, F9) pass --yes; the deny test (F8)
# and the cap test (F7) deliberately omit it and rely on the EOF stdin above.
# (F7 must NOT pass --yes: auto_yes would auto-raise the usd cap instead of
# aborting.)
#
# Requires a real OPENROUTER_API_KEY in .env (compose loads it via env_file).
# These are LIVE model calls; expect a few cents per full run (F5 parallel
# explorers and F6 ~100k-token compaction are priciest; F7 aborts at ~$0).
# Only `docker`, `bash`, and coreutils/grep are required (no jq).
#
# Usage:
#   bash scripts/smoke_live.sh
#   bash scripts/smoke_live.sh --skip-build --only F6,F7
#   bash scripts/smoke_live.sh --keep-fixture

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TRACES_DIR="$PROJECT_ROOT/traces"
WORKSPACE_DIR="$PROJECT_ROOT/workspace"

SKIP_BUILD=0
KEEP_FIXTURE=0
ONLY=()

usage() { grep -E '^#( |$)' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --skip-build)   SKIP_BUILD=1; shift ;;
        --keep-fixture) KEEP_FIXTURE=1; shift ;;
        --only)         IFS=',' read -r -a ONLY <<< "$2"; shift 2 ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "unknown arg: $1 (try --help)" >&2; exit 2 ;;
    esac
done

# Colors only when stdout is a terminal.
if [ -t 1 ]; then
    GREEN=$'\e[32m'; RED=$'\e[31m'; CYAN=$'\e[36m'; DIM=$'\e[2m'; RST=$'\e[0m'
else
    GREEN=""; RED=""; CYAN=""; DIM=""; RST=""
fi

# Prefer `docker compose` (v2); fall back to `docker-compose` (v1).
if docker compose version >/dev/null 2>&1; then
    DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    DC=(docker-compose)
else
    echo "error: neither 'docker compose' nor 'docker-compose' found" >&2
    exit 2
fi

step() { printf '\n%s== %s ==%s\n' "$CYAN" "$1" "$RST"; }

trunc() {
    local s="$1"
    s="${s//$'\r'/}"
    s="${s//$'\n'/ }"
    if [ "${#s}" -le 220 ]; then printf '%s' "$s"; else printf '%s ...' "${s:0:220}"; fi
}

# find_line <file> <needle1> [needle2 ...] -> first line containing ALL needles.
# Returns 1 (and no output) when no line matches.
find_line() {
    local file="$1"; shift
    [ -f "$file" ] || return 1
    local result; result="$(cat "$file")"
    local needle
    for needle in "$@"; do
        result="$(printf '%s\n' "$result" | grep -F -- "$needle")" || return 1
        [ -n "$result" ] || return 1
    done
    printf '%s\n' "$result" | head -n1
}

# --- result accumulation ---------------------------------------------------
RES_LABEL=(); RES_VG=(); RES_PASS=(); RES_RUNID=(); RES_EV=(); RES_TRACE=()
NEW_TRACE_IDS=()

record() {
    # record <label> <vg> <pass:0|1> <evidence> <runid> <tracepath>
    RES_LABEL+=("$1"); RES_VG+=("$2"); RES_PASS+=("$3")
    RES_EV+=("$(trunc "$4")"); RES_RUNID+=("${5:--}"); RES_TRACE+=("${6:-}")
    local tag color
    if [ "$3" -eq 1 ]; then tag="PASS"; color="$GREEN"; else tag="FAIL"; color="$RED"; fi
    printf '  %s%s%s  run=%s  exit=%s\n' "$color" "$tag" "$RST" "${5:-?}" "${LAST_EXIT:-?}"
    printf '  %sevidence: %s%s\n' "$DIM" "$(trunc "$4")" "$RST"
    [ -n "${5:-}" ] && NEW_TRACE_IDS+=("$5")
}

# run_task <docker args...> -> sets LAST_EXIT, LAST_OUT, LAST_RUNID, LAST_TRACE
run_task() {
    LAST_OUT="$(mktemp)"
    # -T disables the pseudo-TTY, and `</dev/null` pins stdin to EOF so any
    # approval prompt reads EOF immediately (deterministic deny/abort) instead
    # of blocking forever on the inherited terminal stdin. Features that must
    # execute a gated tool (run_bash / spawn / edit under
    # VG_APPROVAL_MODE=writes) pass --yes so the tool auto-approves before stdin
    # is ever read. Fold stderr (progress) into the capture for evidence.
    "${DC[@]}" run --rm -T vg-agent "$@" >"$LAST_OUT" 2>&1 </dev/null
    LAST_EXIT=$?
    LAST_RUNID=""; LAST_TRACE=""
    local traceline
    traceline="$(grep -E 'trace:[[:space:]]*[^[:space:]]' "$LAST_OUT" | head -n1)"
    if [[ "$traceline" =~ traces[/\\]([0-9a-fA-F]+)\.jsonl ]]; then
        LAST_RUNID="${BASH_REMATCH[1]}"
        LAST_TRACE="$TRACES_DIR/$LAST_RUNID.jsonl"
    fi
}

should_run() {
    [ "${#ONLY[@]}" -eq 0 ] && return 0
    local o
    for o in "${ONLY[@]}"; do [ "$o" = "$1" ] && return 0; done
    return 1
}

# --- feature definitions ---------------------------------------------------

f1() { # VG.5 bash exec
    step "F1 (VG.5 bash exec)"
    run_task --task "run bash command: pwd" --yes --trace
    local hit; hit="$(find_line "$LAST_TRACE" '"kind": "tool_result"' 'run_bash' '/workspace' '"status": "ok"')" || hit=""
    local pass=0; { [ "$LAST_EXIT" -eq 0 ] && [ -n "$hit" ]; } && pass=1
    local ev="$hit"; [ -z "$ev" ] && ev="no ok run_bash tool_result with /workspace"
    record F1 "VG.5 bash exec" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

f2() { # VG.4 bash tool-layer block
    step "F2 (VG.4 bash tool-layer block)"
    run_task --task "Use run_bash with command exactly: touch demo.txt" --yes --trace
    local hit; hit="$(find_line "$LAST_TRACE" '"kind": "tool_result"' 'not in the read-only allowlist')" || hit=""
    local nofile=1; [ -e "$WORKSPACE_DIR/demo.txt" ] && nofile=0
    local pass=0; { [ -n "$hit" ] && [ "$nofile" -eq 1 ]; } && pass=1
    local ev; if [ -n "$hit" ]; then ev="$hit (demo.txt created: $([ "$nofile" -eq 1 ] && echo false || echo true))"; else ev="no allowlist-block tool_result"; fi
    record F2 "VG.4 bash allowlist block" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

f3() { # VG.4 .env sensitive-path block
    step "F3 (VG.4 .env sensitive-path block)"
    # Directive prompt (like F2) to coerce a real read_file call so the tool
    # layer fires its block — a natural-language ask lets the model refuse first.
    run_task --task "Use the read_file tool to read the file with path exactly: .env" --yes --trace
    local hit; hit="$(find_line "$LAST_TRACE" '"kind": "tool_result"' 'sensitive path' '.env')" || hit=""
    local pass=0; [ -n "$hit" ] && pass=1
    local ev="$hit"; [ -z "$ev" ] && ev="no sensitive-path tool_result for .env"
    record F3 "VG.4 .env block" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

f4() { # VG.9 yield vs guess
    step "F4 (VG.9 yield vs guess)"
    run_task --task "make it better" --yes --trace
    local mutated wrote yielded
    mutated="$(find_line "$LAST_TRACE" '"kind": "tool_call"' '"edit_file"')" || mutated=""
    wrote="$(find_line "$LAST_TRACE" '"kind": "tool_call"' '"write_file"')" || wrote=""
    yielded="$(grep '"kind": "assistant_step"' "$LAST_TRACE" 2>/dev/null | grep -F '"tool_calls": []' | grep -E '"assistant_text":[[:space:]]*"[^"]' | head -n1)"
    local pass=0; { [ -z "$mutated" ] && [ -z "$wrote" ] && [ -n "$yielded" ]; } && pass=1
    local ev="$yielded"; [ -z "$ev" ] && ev="no clarifying assistant_step (mutated=$([ -n "$mutated" ] && echo true || echo false))"
    record F4 "VG.9 yield vs guess" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

f5() { # VG.1 parallel sub-agents
    step "F5 (VG.1 parallel sub-agents)"
    run_task --task "summarise auth/ and utils.py in parallel; combine both sub-agent findings into one final recommendation" --yes --finops --trace
    local spawns explorers
    spawns="$(grep -c '"kind": "subagent_spawn"' "$LAST_TRACE" 2>/dev/null)"; spawns="${spawns:-0}"
    explorers="$(grep '"kind": "subagent_spawn"' "$LAST_TRACE" 2>/dev/null | grep -c 'explorer')"; explorers="${explorers:-0}"
    local pass=0; { [ "$explorers" -ge 2 ] && [ "$LAST_EXIT" -eq 0 ]; } && pass=1
    record F5 "VG.1 parallel sub-agents" "$pass" "$spawns subagent_spawn ($explorers explorer)" "$LAST_RUNID" "$LAST_TRACE"
}

f6() { # VG.2 context compaction
    step "F6 (VG.2 context compaction)"
    run_task --task "Do not spawn a sub-agent. Use the parent read_file tool to read data/sample.log directly, then summarise the important pattern in one sentence." --yes --show-context 3 --trace
    local comp before after marker
    comp="$(grep -F '"kind": "compaction"' "$LAST_TRACE" 2>/dev/null | head -n1)"
    before=0; after=-1
    if [ -n "$comp" ]; then
        before="$(printf '%s' "$comp" | grep -oE '"before_tokens":[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -n1)"; before="${before:-0}"
        after="$(printf '%s' "$comp" | grep -oE '"after_tokens":[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -n1)"; after="${after:--1}"
    fi
    marker=false; grep -qF '[COMPACTED tool_result' "$LAST_OUT" 2>/dev/null && marker=true
    local pass=0; { [ -n "$comp" ] && [ "$before" -gt 4000 ] && [ "$after" -lt "$before" ]; } && pass=1
    record F6 "VG.2 context compaction" "$pass" "compaction before=$before after=$after show-context-marker=$marker" "$LAST_RUNID" "$LAST_TRACE"
}

f7() { # VG.3 hard cap (usd_cap)
    step "F7 (VG.3 hard cap usd_cap)"
    run_task --task "review app.py" --max-usd 0.01 --budget --trace
    local cap abort
    cap="$(find_line "$LAST_TRACE" '"kind": "budget_event"' 'usd_cap')" || cap=""
    abort="$(find_line "$LAST_TRACE" '"kind": "run_end"' '"final_status": "aborted"')" || abort=""
    local pass=0; { [ "$LAST_EXIT" -eq 3 ] && [ -n "$cap" ] && [ -n "$abort" ]; } && pass=1
    local ev="$cap"; [ -z "$ev" ] && ev="no usd_cap budget_event (exit=$LAST_EXIT)"
    record F7 "VG.3 hard cap" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

f8() { # VG.4/VG.6 approval DENY
    step "F8 (VG.4/VG.6 approval DENY)"
    run_task --task "edit app.py to add a new debug function" --require-approval writes --trace
    local denied okedit unchanged=0
    denied="$(find_line "$LAST_TRACE" '"kind": "approval"' 'denied')" || denied=""
    okedit="$(find_line "$LAST_TRACE" '"kind": "tool_result"' 'edit_file' '"status": "ok"')" || okedit=""
    grep -qE 'def[[:space:]]+foo' "$WORKSPACE_DIR/app.py" 2>/dev/null && unchanged=1
    local pass=0; { [ -n "$denied" ] && [ -z "$okedit" ] && [ "$unchanged" -eq 1 ]; } && pass=1
    local ev; if [ -n "$denied" ]; then ev="$denied (app.py still def foo: $([ "$unchanged" -eq 1 ] && echo true || echo false))"; else ev="no denied approval"; fi
    record F8 "VG.4/VG.6 approval deny" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

f9() { # VG.6 partial edit APPROVE
    step "F9 (VG.6 partial edit APPROVE)"
    run_task --task "use bash to confirm the workspace path, then rename foo to bar in app.py using the smallest possible edit" --yes --require-approval writes --trace
    local auto okedit changed=0
    auto="$(find_line "$LAST_TRACE" '"kind": "approval"' '"auto"')" || auto=""
    okedit="$(find_line "$LAST_TRACE" '"kind": "tool_result"' 'edit_file' '"status": "ok"')" || okedit=""
    grep -qE 'def[[:space:]]+bar' "$WORKSPACE_DIR/app.py" 2>/dev/null && changed=1
    local pass=0; { [ -n "$auto" ] && [ -n "$okedit" ] && [ "$changed" -eq 1 ] && [ "$LAST_EXIT" -eq 0 ]; } && pass=1
    local ev; if [ -n "$okedit" ]; then ev="$okedit (app.py now def bar: $([ "$changed" -eq 1 ] && echo true || echo false))"; else ev="no successful edit_file"; fi
    record F9 "VG.6 partial edit approve" "$pass" "$ev" "$LAST_RUNID" "$LAST_TRACE"
}

# --- preflight -------------------------------------------------------------
cd "$PROJECT_ROOT"

step "Preflight"
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "error: .env not found. Copy .env.example to .env and set OPENROUTER_API_KEY (live calls)." >&2
    exit 2
fi
if ! grep -qE '^[[:space:]]*OPENROUTER_API_KEY=[^[:space:]]' "$PROJECT_ROOT/.env"; then
    echo "error: OPENROUTER_API_KEY not set in .env (live calls)." >&2
    exit 2
fi
echo "  .env present with OPENROUTER_API_KEY"
mkdir -p "$WORKSPACE_DIR" "$TRACES_DIR"

if [ "$SKIP_BUILD" -eq 0 ]; then
    step "docker compose build"
    "${DC[@]}" build
fi
if [ "$KEEP_FIXTURE" -eq 0 ]; then
    step "Seed clean fixture (resets workspace/app.py to def foo)"
    "${DC[@]}" run --rm -T vg-agent --seed-fixture >/dev/null
fi

# --- feature matrix --------------------------------------------------------
# Order: read-only / abort tests first, then deny-edit BEFORE approve-edit
# (the approve case mutates app.py last). Prompts mirror docs/demo/quick_demo.md.
should_run F1 && f1
should_run F2 && f2
should_run F3 && f3
should_run F4 && f4
should_run F5 && f5
should_run F6 && f6
should_run F7 && f7
should_run F8 && f8
should_run F9 && f9

# --- post-suite: secret scan over this run's traces ------------------------
step "Secret scan (redaction regression check)"
SECRET_RX='sk-or-v1|OPENROUTER_API_KEY=.+|Bearer [A-Za-z0-9._-]+|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|PRIVATE) KEY'
leak_hits=0; first_leak=""; scanned_ids=()
for id in $(printf '%s\n' "${NEW_TRACE_IDS[@]:-}" | sort -u); do
    [ -z "$id" ] && continue
    p="$TRACES_DIR/$id.jsonl"
    [ -f "$p" ] || continue
    scanned_ids+=("$id")
    m="$(grep -nE "$SECRET_RX" "$p" | head -n1)"
    if [ -n "$m" ]; then leak_hits=$((leak_hits+1)); [ -z "$first_leak" ] && first_leak="$p: $m"; fi
done
sec_pass=0; [ "$leak_hits" -eq 0 ] && sec_pass=1
if [ "$sec_pass" -eq 1 ]; then printf '  %sPASS%s  0 leak hit(s)\n' "$GREEN" "$RST"; else printf '  %sFAIL%s  %s leak hit(s)\n' "$RED" "$RST" "$leak_hits"; fi
sec_ev="no key-shaped strings in ${#scanned_ids[@]} traces"; [ "$sec_pass" -eq 0 ] && sec_ev="LEAK: $first_leak"
# Run id column lists the traces this scan actually covered (it derives from the
# earlier live runs rather than a run of its own); fall back to "-" if none.
sec_runid="$(IFS=,; printf '%s' "${scanned_ids[*]:-}")"; [ -z "$sec_runid" ] && sec_runid="-"
RES_LABEL+=("SEC"); RES_VG+=("VG.8 no secret leak in traces"); RES_PASS+=("$sec_pass"); RES_EV+=("$(trunc "$sec_ev")"); RES_RUNID+=("$sec_runid"); RES_TRACE+=("")

# --- config / packaging presence (no live call) ----------------------------
cfg_pass=0; { [ -f "$PROJECT_ROOT/config.example.toml" ] && [ -f "$PROJECT_ROOT/.env.example" ]; } && cfg_pass=1
pkg_pass=0; { [ -f "$PROJECT_ROOT/Dockerfile" ] && [ -f "$PROJECT_ROOT/docker-compose.yml" ]; } && pkg_pass=1
RES_LABEL+=("CFG"); RES_VG+=("VG.8 config/.env split"); RES_PASS+=("$cfg_pass"); RES_EV+=("config.example.toml + .env.example present: $([ "$cfg_pass" -eq 1 ] && echo true || echo false)"); RES_RUNID+=("-"); RES_TRACE+=("")
RES_LABEL+=("PKG"); RES_VG+=("VG.7 packaging"); RES_PASS+=("$pkg_pass"); RES_EV+=("Dockerfile + docker-compose.yml present; all runs went through compose"); RES_RUNID+=("-"); RES_TRACE+=("")

# best-effort warn_usd note (non-fatal)
warn_seen=false
for id in $(printf '%s\n' "${NEW_TRACE_IDS[@]:-}" | sort -u); do
    [ -z "$id" ] && continue
    if grep -q 'warn_usd' "$TRACES_DIR/$id.jsonl" 2>/dev/null; then warn_seen=true; break; fi
done

# --- report ----------------------------------------------------------------
pass_count=0; fail_count=0
for p in "${RES_PASS[@]}"; do [ "$p" -eq 1 ] && pass_count=$((pass_count+1)) || fail_count=$((fail_count+1)); done

REPORT="$TRACES_DIR/smoke_report.md"
{
    echo "# vg_agent live smoke report"
    echo
    echo "- Generated: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "- Runner: \`${DC[*]} run --rm -T vg-agent\` (canonical packaging path)"
    echo "- Result: **$pass_count passed / $fail_count failed**"
    echo "- warn_usd observed this run: $warn_seen (best-effort, non-fatal)"
    echo
    if [ -f "$PROJECT_ROOT/config.example.toml" ]; then
        echo "Configured models (from config.example.toml):"
        echo '```toml'
        awk '/^[[:space:]]*\[models\]/{f=1;print;next} f&&/^[[:space:]]*\[/{exit} f{print}' "$PROJECT_ROOT/config.example.toml"
        echo '```'
        echo
    fi
    echo "| Feature | VG | Result | Run id | Evidence |"
    echo "|---|---|---|---|---|"
    for i in "${!RES_LABEL[@]}"; do
        res="FAIL"; [ "${RES_PASS[$i]}" -eq 1 ] && res="PASS"
        ev="${RES_EV[$i]//|/\\|}"
        echo "| ${RES_LABEL[$i]} | ${RES_VG[$i]} | $res | ${RES_RUNID[$i]} | $ev |"
    done
    echo
    echo "## Analyzing failures"
    echo
    echo "Each run's full evidence is in its JSONL trace under \`traces/<run id>.jsonl\`."
    echo "Open a failing run's trace, or ask Claude Code to inspect it, e.g.:"
    echo
    echo '```'
    for i in "${!RES_LABEL[@]}"; do
        if [ "${RES_PASS[$i]}" -eq 0 ] && [ -n "${RES_TRACE[$i]}" ]; then
            echo "traces/${RES_RUNID[$i]}.jsonl   # ${RES_LABEL[$i]} ${RES_VG[$i]}"
        fi
    done
    echo '```'
} > "$REPORT"

step "Summary"
for i in "${!RES_LABEL[@]}"; do
    res="FAIL"; color="$RED"; [ "${RES_PASS[$i]}" -eq 1 ] && { res="PASS"; color="$GREEN"; }
    printf '  %s%-4s%s %-32s %srun=%s%s\n' "$color" "$res" "$RST" "${RES_VG[$i]}" "$DIM" "${RES_RUNID[$i]}" "$RST"
done
if [ "$fail_count" -eq 0 ]; then printf '%s%s passed / %s failed%s\n' "$GREEN" "$pass_count" "$fail_count" "$RST"; else printf '%s%s passed / %s failed%s\n' "$RED" "$pass_count" "$fail_count" "$RST"; fi
echo "Report: $REPORT"

[ "$fail_count" -gt 0 ] && exit 1
exit 0
