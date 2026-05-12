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

Step "Done"
Write-Host "Use the printed trace path from the VG slide run for replay:" -ForegroundColor Green
Write-Host "uv run --project $ProjectRoot python -m vg_agent --replay fixtures/demo_repo/traces/<run_id>.jsonl --trace --show-context 3"
Pop-Location
