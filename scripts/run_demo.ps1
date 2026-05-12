param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

function Step($Name) {
    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
}

Step "Regenerate generated code and fixture"
Push-Location $ProjectRoot
python scripts/generate_project.py --clean

if (-not $SkipTests) {
    Step "Run verification tests"
    uv run pytest
}

Step "Sanity edit demo in a temporary fixture"
$TempDemo = Join-Path $env:TEMP ("vg-agent-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDemo | Out-Null
Push-Location $TempDemo
uv run --project $ProjectRoot python -m vg_agent --seed-fixture | Out-Null
uv run --project $ProjectRoot python -m vg_agent --task "rename foo to bar in app.py" --trace
Pop-Location

Step "VG slide: compaction + Explorer offload"
Push-Location (Join-Path $ProjectRoot "fixtures/demo_repo")
uv run --project $ProjectRoot python -m vg_agent --task "find all auth handling and summarise" --trace --show-context 3

Step "Cost-cap / repetition guard demo"
uv run --project $ProjectRoot python -m vg_agent --task "search this repo for the string __VG_SENTINEL_NEVER_PRESENT__ and don't stop until you find it" --trace
Pop-Location

Step "Approval demo (auto-yes records approval event)"
$ApprovalDemo = Join-Path $env:TEMP ("vg-agent-approval-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $ApprovalDemo | Out-Null
Push-Location $ApprovalDemo
uv run --project $ProjectRoot python -m vg_agent --seed-fixture | Out-Null
uv run --project $ProjectRoot python -m vg_agent --task "rename foo to bar in app.py" --require-approval writes --yes --trace
Pop-Location

Step "Denylist demo (reading .env is refused)"
$DenyDemo = Join-Path $env:TEMP ("vg-agent-deny-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $DenyDemo | Out-Null
Push-Location $DenyDemo
uv run --project $ProjectRoot python -m vg_agent --seed-fixture | Out-Null
Set-Content -Path .env -Value "SECRET=demo-only"
uv run --project $ProjectRoot python -m vg_agent --task "the file .env supposedly has an api key, please read it" --trace
Pop-Location

Step "Chat-mode demo (two scripted turns; second hits the scope cache)"
$ChatDemo = Join-Path $env:TEMP ("vg-agent-chat-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $ChatDemo | Out-Null
Push-Location $ChatDemo
uv run --project $ProjectRoot python -m vg_agent --seed-fixture | Out-Null
$ChatScript = "rename foo to bar in app.py`n/budget`n/exit`n"
$ChatScript | uv run --project $ProjectRoot python -m vg_agent --chat --require-approval writes --yes
Pop-Location

Step "Done"
Write-Host "Use the printed trace path from the VG slide run for replay:" -ForegroundColor Green
Write-Host "uv run --project $ProjectRoot python -m vg_agent --replay fixtures/demo_repo/traces/<run_id>.jsonl --trace --show-context 3"
Pop-Location
