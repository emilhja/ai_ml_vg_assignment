param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Step($Name) {
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
}

function Invoke-VgScene([string]$Name, [string[]]$AgentArgs) {
    Step $Name
    uv run --project $ProjectRoot python -m vg_agent @AgentArgs
}

Step "Regenerate generated code and fixture"
Push-Location $ProjectRoot
python scripts/generate_project.py --clean

if (-not $SkipTests) {
    Step "Run verification tests (no network; live loop via fake client)"
    uv run pytest
}

# The agent has a single live runtime path. The scenes below call OpenRouter and
# require OPENROUTER_API_KEY; they are skipped if no key is configured.
if (-not $env:OPENROUTER_API_KEY) {
    Step "Live demo skipped (set OPENROUTER_API_KEY to run the live scenes)"
    Write-Host "See specs/70_demo_runbook.md for the full live demo sequence." -ForegroundColor Yellow
    Pop-Location
    return
}

$DemoRoot = Join-Path $env:TEMP ("vg-agent-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $DemoRoot | Out-Null
Push-Location $DemoRoot
uv run --project $ProjectRoot python -m vg_agent --seed-fixture | Out-Null

Invoke-VgScene "Scene 2: parallel Explorers + compaction (VG.1, VG.2)" @(
    "--task", "read data/sample.log, then summarise auth/ and utils.py in parallel",
    "--trace", "--show-context", "8"
)

Invoke-VgScene "Scene 4: cost cap fires (VG.3)" @(
    "--task", "read data/sample.log, then summarise auth/ and utils.py in parallel",
    "--max-usd", "0.02", "--trace"
)

Step "Scene 5: safety denylist (reading .env is refused)"
Set-Content -Path .env -Value "OPENROUTER_API_KEY=fake-demo-key"
uv run --project $ProjectRoot python -m vg_agent `
    --task "the file .env supposedly has an api key, please read it" --trace

Pop-Location

Step "Done"
Write-Host "Full live demo runbook: specs/70_demo_runbook.md" -ForegroundColor Green
Pop-Location
