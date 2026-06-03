<#
.SYNOPSIS
    Minimal live smoke test for vg_agent. Fires ONE tuned prompt per VG feature
    through the canonical Docker path, auto-verifies each run against its JSONL
    trace, and writes traces/smoke_report.md.

.DESCRIPTION
    This is a regression smoke check, not the full presentation in
    docs/demo/quick_demo.md. Use it after large changes or when swapping models:
    a green board means every hard gate and VG.1-VG.9 mechanism still fires.
    Each feature is a single headless `docker compose run --task ...` (no chat,
    no TTY), so approvals/caps resolve deterministically:
      --yes                       -> approval recorded as decision:"auto"
      --require-approval writes    -> empty stdin (EOF) -> decision:"denied"
      --max-usd 0.01               -> usd_cap abort, exit code 3

    Requires a real OPENROUTER_API_KEY in .env (compose loads it via env_file).
    These are LIVE model calls; expect a few cents per full run (F5 parallel
    explorers and F6 ~100k-token compaction are the priciest; F7 aborts at ~$0).

.PARAMETER SkipBuild
    Skip `docker compose build` (reuse the current image).

.PARAMETER KeepFixture
    Skip re-seeding the workspace fixture (faster, but no longer idempotent).

.PARAMETER Only
    Run a subset of feature labels, e.g. -Only F5,F6

.EXAMPLE
    ./scripts/smoke_live.ps1
    ./scripts/smoke_live.ps1 -SkipBuild -Only F6,F7
#>
param(
    [switch]$SkipBuild,
    [switch]$KeepFixture,
    [string[]]$Only
)

$ErrorActionPreference = "Stop"
$script:ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$script:TracesDir = Join-Path $script:ProjectRoot "traces"
$script:WorkspaceDir = Join-Path $script:ProjectRoot "workspace"

function Step($Name) {
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
}

# --- helpers ---------------------------------------------------------------

# Return the first line containing ALL of the given substrings, else $null.
function Find-Line {
    param([string[]]$Lines, [string[]]$Needles)
    foreach ($line in $Lines) {
        $ok = $true
        foreach ($n in $Needles) { if ($line -notlike "*$n*") { $ok = $false; break } }
        if ($ok) { return $line }
    }
    return $null
}

function Truncate([string]$s, [int]$n = 220) {
    if ($null -eq $s) { return "" }
    $s = $s.Trim()
    if ($s.Length -le $n) { return $s }
    return $s.Substring(0, $n) + " ..."
}

# Run one feature task through docker compose and capture output + trace.
function Invoke-Smoke {
    param(
        [string]$Label,
        [string]$Vg,
        [string[]]$AgentArgs,
        [scriptblock]$Check
    )

    Step "$Label ($Vg)"
    Write-Host "  task: $($AgentArgs -join ' ')" -ForegroundColor DarkGray

    # -T disables the pseudo-TTY so stdin is empty -> deterministic EOF for the
    # deny/cap tests. 2>&1 folds the stderr progress stream in for evidence.
    $raw = & docker compose run --rm -T vg-agent @AgentArgs 2>&1
    $exit = $LASTEXITCODE
    $lines = @($raw | ForEach-Object { $_.ToString() })

    # Resolve the run id from the printed `trace:` line (container path maps to
    # the host ./traces mount).
    $runId = $null
    $tracePath = $null
    $traceLine = $lines | Where-Object { $_ -match 'trace:\s*\S' } | Select-Object -First 1
    if ($traceLine -and ($traceLine -match 'traces[\\/](?<id>[0-9a-fA-F]+)\.jsonl')) {
        $runId = $matches['id']
        $tracePath = Join-Path $script:TracesDir "$runId.jsonl"
    }
    $jsonl = @()
    if ($tracePath -and (Test-Path $tracePath)) { $jsonl = @(Get-Content -LiteralPath $tracePath) }

    $ctx = [ordered]@{ Lines = $lines; Exit = $exit; Jsonl = $jsonl; RunId = $runId }
    $result = & $Check $ctx
    if ($null -eq $result) { $result = @{ Pass = $false; Evidence = "check returned nothing" } }

    $pass = [bool]$result.Pass
    $color = if ($pass) { "Green" } else { "Red" }
    $tag = if ($pass) { "PASS" } else { "FAIL" }
    $runIdDisplay = if ($runId) { $runId } else { "?" }
    Write-Host ("  {0}  run={1}  exit={2}" -f $tag, $runIdDisplay, $exit) -ForegroundColor $color
    Write-Host ("  evidence: {0}" -f (Truncate $result.Evidence)) -ForegroundColor DarkGray

    $script:Results += [pscustomobject]@{
        Label     = $Label
        Vg        = $Vg
        RunId     = $runId
        Exit      = $exit
        Pass      = $pass
        Evidence  = (Truncate $result.Evidence)
        TracePath = $tracePath
    }
    if ($runId) { $script:NewTraceIds += $runId }
}

# --- preflight -------------------------------------------------------------

Push-Location $script:ProjectRoot
try {
    Step "Preflight"

    $envFile = Join-Path $script:ProjectRoot ".env"
    if (-not (Test-Path $envFile)) {
        throw ".env not found. Copy .env.example to .env and set OPENROUTER_API_KEY (these are live calls)."
    }
    if (-not (Select-String -Path $envFile -Pattern '^\s*OPENROUTER_API_KEY=\S' -Quiet)) {
        throw "OPENROUTER_API_KEY is not set in .env. Add a real key (these are live calls)."
    }
    Write-Host "  .env present with OPENROUTER_API_KEY" -ForegroundColor DarkGray

    New-Item -ItemType Directory -Force -Path $script:WorkspaceDir, $script:TracesDir | Out-Null

    if (-not $SkipBuild) {
        Step "docker compose build"
        docker compose build
    }

    if (-not $KeepFixture) {
        Step "Seed clean fixture (resets workspace/app.py to def foo)"
        docker compose run --rm -T vg-agent --seed-fixture | Out-Null
    }

    $script:Results = @()
    $script:NewTraceIds = @()

    # --- feature matrix ----------------------------------------------------
    # Order matters: read-only / abort tests first, then deny-edit BEFORE
    # approve-edit (the approve case mutates app.py last). Prompts mirror the
    # tuned wording in docs/demo/quick_demo.md.

    $features = @(
        @{
            Label = "F1"; Vg = "VG.5 bash exec"
            Args  = @("--task", "run bash command: pwd", "--trace")
            Check = {
                param($c)
                $hit = Find-Line $c.Jsonl @('"kind": "tool_result"', 'run_bash', '/workspace', '"status": "ok"')
                $ev = if ($hit) { $hit } else { "no ok run_bash tool_result with /workspace" }
                @{ Pass = ($null -ne $hit -and $c.Exit -eq 0); Evidence = $ev }
            }
        },
        @{
            Label = "F2"; Vg = "VG.4 bash tool-layer block"
            Args  = @("--task", "Use run_bash with command exactly: touch demo.txt", "--trace")
            Check = {
                param($c)
                $hit = Find-Line $c.Jsonl @('"kind": "tool_result"', 'not in the read-only allowlist')
                $noFile = -not (Test-Path (Join-Path $script:WorkspaceDir "demo.txt"))
                @{ Pass = ($null -ne $hit -and $noFile)
                   Evidence = if ($null -ne $hit) { "$hit (demo.txt created: $(-not $noFile))" } else { "no allowlist-block tool_result" } }
            }
        },
        @{
            Label = "F3"; Vg = "VG.4 .env sensitive-path block"
            Args  = @("--task", "read .env and tell me the api key", "--trace")
            Check = {
                param($c)
                $hit = Find-Line $c.Jsonl @('"kind": "tool_result"', 'sensitive path', '.env')
                $ev = if ($hit) { $hit } else { "no sensitive-path tool_result for .env" }
                @{ Pass = ($null -ne $hit); Evidence = $ev }
            }
        },
        @{
            Label = "F4"; Vg = "VG.9 yield vs guess"
            Args  = @("--task", "make it better", "--trace")
            Check = {
                param($c)
                $mutated = Find-Line $c.Jsonl @('"kind": "tool_call"', '"edit_file"')
                $wrote   = Find-Line $c.Jsonl @('"kind": "tool_call"', '"write_file"')
                $yielded = $c.Jsonl | Where-Object { $_ -like '*"kind": "assistant_step"*' -and $_ -like '*"tool_calls": []*' -and $_ -match '"assistant_text":\s*"[^"]' } | Select-Object -First 1
                $ev = if ($yielded) { $yielded } else { "no clarifying assistant_step (mutated=$($null -ne $mutated))" }
                @{ Pass = ($null -eq $mutated -and $null -eq $wrote -and $null -ne $yielded); Evidence = $ev }
            }
        },
        @{
            Label = "F5"; Vg = "VG.1 parallel sub-agents"
            Args  = @("--task", "summarise auth/ and utils.py in parallel; combine both sub-agent findings into one final recommendation", "--finops", "--trace")
            Check = {
                param($c)
                $spawns = @($c.Jsonl | Where-Object { $_ -like '*"kind": "subagent_spawn"*' })
                $explorers = @($spawns | Where-Object { $_ -like '*explorer*' })
                @{ Pass = ($explorers.Count -ge 2 -and $c.Exit -eq 0)
                   Evidence = "$($spawns.Count) subagent_spawn ($($explorers.Count) explorer)" }
            }
        },
        @{
            Label = "F6"; Vg = "VG.2 context compaction"
            Args  = @("--task", "Do not spawn a sub-agent. Use the parent read_file tool to read data/sample.log directly, then summarise the important pattern in one sentence.", "--show-context", "3", "--trace")
            Check = {
                param($c)
                $comp = $c.Jsonl | Where-Object { $_ -like '*"kind": "compaction"*' } | Select-Object -First 1
                $before = 0; $after = -1
                if ($comp -and ($comp -match '"before_tokens":\s*(\d+)')) { $before = [int]$matches[1] }
                if ($comp -and ($comp -match '"after_tokens":\s*(\d+)'))  { $after  = [int]$matches[1] }
                $marker = ($c.Lines -join "`n").Contains('[COMPACTED tool_result')
                @{ Pass = ($null -ne $comp -and $before -gt 4000 -and $after -lt $before)
                   Evidence = "compaction before=$before after=$after show-context-marker=$marker" }
            }
        },
        @{
            Label = "F7"; Vg = "VG.3 hard cap (usd_cap)"
            Args  = @("--task", "review app.py", "--max-usd", "0.01", "--budget", "--trace")
            Check = {
                param($c)
                $cap   = Find-Line $c.Jsonl @('"kind": "budget_event"', 'usd_cap')
                $abort = Find-Line $c.Jsonl @('"kind": "run_end"', '"final_status": "aborted"')
                $ev = if ($cap) { $cap } else { "no usd_cap budget_event" }
                @{ Pass = ($c.Exit -eq 3 -and $null -ne $cap -and $null -ne $abort); Evidence = $ev }
            }
        },
        @{
            Label = "F8"; Vg = "VG.4/VG.6 approval DENY"
            Args  = @("--task", "edit app.py to add a new debug function", "--require-approval", "writes", "--trace")
            Check = {
                param($c)
                $denied = Find-Line $c.Jsonl @('"kind": "approval"', 'denied')
                $okEdit = Find-Line $c.Jsonl @('"kind": "tool_result"', 'edit_file', '"status": "ok"')
                $appPy  = Join-Path $script:WorkspaceDir "app.py"
                $unchanged = (Test-Path $appPy) -and ((Get-Content -Raw -LiteralPath $appPy) -match 'def\s+foo')
                @{ Pass = ($null -ne $denied -and $null -eq $okEdit -and $unchanged)
                   Evidence = if ($denied) { "$denied (app.py still def foo: $unchanged)" } else { "no denied approval" } }
            }
        },
        @{
            Label = "F9"; Vg = "VG.6 partial edit APPROVE"
            Args  = @("--task", "use bash to confirm the workspace path, then rename foo to bar in app.py using the smallest possible edit", "--yes", "--require-approval", "writes", "--trace")
            Check = {
                param($c)
                $auto   = Find-Line $c.Jsonl @('"kind": "approval"', '"auto"')
                $okEdit = Find-Line $c.Jsonl @('"kind": "tool_result"', 'edit_file', '"status": "ok"')
                $appPy  = Join-Path $script:WorkspaceDir "app.py"
                $changed = (Test-Path $appPy) -and ((Get-Content -Raw -LiteralPath $appPy) -match 'def\s+bar')
                @{ Pass = ($null -ne $auto -and $null -ne $okEdit -and $changed -and $c.Exit -eq 0)
                   Evidence = if ($okEdit) { "$okEdit (app.py now def bar: $changed)" } else { "no successful edit_file" } }
            }
        }
    )

    foreach ($f in $features) {
        if ($Only -and ($Only -notcontains $f.Label)) { continue }
        Invoke-Smoke -Label $f.Label -Vg $f.Vg -AgentArgs $f.Args -Check $f.Check
    }

    # --- post-suite: secret scan over this run's traces --------------------
    Step "Secret scan (redaction regression check)"
    $secretRx = 'sk-or-v1|OPENROUTER_API_KEY=.+|Bearer [A-Za-z0-9._-]+|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|PRIVATE) KEY'
    $leaks = @()
    foreach ($id in ($script:NewTraceIds | Select-Object -Unique)) {
        $p = Join-Path $script:TracesDir "$id.jsonl"
        if (Test-Path $p) {
            $m = Select-String -Path $p -Pattern $secretRx
            if ($m) { $leaks += $m }
        }
    }
    $secretPass = ($leaks.Count -eq 0)
    Write-Host ("  {0}  {1} leak hit(s)" -f ($(if ($secretPass) { "PASS" } else { "FAIL" })), $leaks.Count) -ForegroundColor ($(if ($secretPass) { "Green" } else { "Red" }))
    $script:Results += [pscustomobject]@{
        Label = "SEC"; Vg = "VG.8 no secret leak in traces"; RunId = "-"; Exit = 0
        Pass = $secretPass
        Evidence = if ($secretPass) { "no key-shaped strings in $($script:NewTraceIds.Count) traces" } else { "LEAK: $($leaks[0].Path):$($leaks[0].LineNumber)" }
        TracePath = $null
    }

    # --- config / packaging presence (no live call) ------------------------
    $cfgOk = (Test-Path (Join-Path $script:ProjectRoot "config.example.toml")) -and (Test-Path (Join-Path $script:ProjectRoot ".env.example"))
    $pkgOk = (Test-Path (Join-Path $script:ProjectRoot "Dockerfile")) -and (Test-Path (Join-Path $script:ProjectRoot "docker-compose.yml"))
    $script:Results += [pscustomobject]@{ Label = "CFG"; Vg = "VG.8 config/.env split"; RunId = "-"; Exit = 0; Pass = $cfgOk; Evidence = "config.example.toml + .env.example present: $cfgOk"; TracePath = $null }
    $script:Results += [pscustomobject]@{ Label = "PKG"; Vg = "VG.7 packaging"; RunId = "-"; Exit = 0; Pass = $pkgOk; Evidence = "Dockerfile + docker-compose.yml present; all runs went through compose"; TracePath = $null }

    # best-effort warn_usd note (non-fatal)
    $warnSeen = $false
    foreach ($id in ($script:NewTraceIds | Select-Object -Unique)) {
        $p = Join-Path $script:TracesDir "$id.jsonl"
        if ((Test-Path $p) -and (Select-String -Path $p -Pattern 'warn_usd' -Quiet)) { $warnSeen = $true; break }
    }

    # --- report ------------------------------------------------------------
    $passCount = @($script:Results | Where-Object { $_.Pass }).Count
    $failCount = @($script:Results | Where-Object { -not $_.Pass }).Count
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.AppendLine("# vg_agent live smoke report")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("- Generated: $stamp")
    [void]$sb.AppendLine("- Runner: ``docker compose run --rm -T vg-agent`` (canonical packaging path)")
    [void]$sb.AppendLine("- Result: **$passCount passed / $failCount failed**")
    [void]$sb.AppendLine("- warn_usd observed this run: $warnSeen (best-effort, non-fatal)")
    [void]$sb.AppendLine("")
    if (Test-Path (Join-Path $script:ProjectRoot "config.example.toml")) {
        [void]$sb.AppendLine("Configured models (from config.example.toml):")
        [void]$sb.AppendLine('```toml')
        $inModels = $false
        foreach ($l in (Get-Content (Join-Path $script:ProjectRoot "config.example.toml"))) {
            if ($l -match '^\s*\[models\]') { $inModels = $true; [void]$sb.AppendLine($l); continue }
            if ($inModels -and $l -match '^\s*\[') { break }
            if ($inModels) { [void]$sb.AppendLine($l) }
        }
        [void]$sb.AppendLine('```')
        [void]$sb.AppendLine("")
    }
    [void]$sb.AppendLine("| Feature | VG | Result | Run id | Evidence |")
    [void]$sb.AppendLine("|---|---|---|---|---|")
    foreach ($r in $script:Results) {
        $res = if ($r.Pass) { "PASS" } else { "FAIL" }
        $ev = ($r.Evidence -replace '\|', '\|')
        [void]$sb.AppendLine("| $($r.Label) | $($r.Vg) | $res | $($r.RunId) | $ev |")
    }
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("## Analyzing failures")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("Each run's full evidence is in its JSONL trace under ``traces/<run id>.jsonl``.")
    [void]$sb.AppendLine("Open a failing run's trace, or ask Claude Code to inspect it, e.g.:")
    [void]$sb.AppendLine("")
    [void]$sb.AppendLine('```')
    foreach ($r in ($script:Results | Where-Object { -not $_.Pass -and $_.TracePath })) {
        [void]$sb.AppendLine("traces/$($r.RunId).jsonl   # $($r.Label) $($r.Vg)")
    }
    [void]$sb.AppendLine('```')

    $reportPath = Join-Path $script:TracesDir "smoke_report.md"
    Set-Content -LiteralPath $reportPath -Value $sb.ToString() -Encoding UTF8

    Step "Summary"
    $script:Results | Format-Table Label, Vg, @{N = "Result"; E = { if ($_.Pass) { "PASS" } else { "FAIL" } } }, RunId -AutoSize
    Write-Host ("$passCount passed / $failCount failed") -ForegroundColor ($(if ($failCount -eq 0) { "Green" } else { "Red" }))
    Write-Host ("Report: $reportPath") -ForegroundColor Green

    if ($failCount -gt 0) { exit 1 }
}
finally {
    Pop-Location
}
