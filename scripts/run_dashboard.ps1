# Start VG Agent trace dashboard (API + Vite dev server).
param(
    [string]$WorkspaceRoot = "workspace",
    [int]$ApiPort = 8787
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$env:VG_WORKSPACE_ROOT = $WorkspaceRoot
$env:VG_DASHBOARD_PORT = "$ApiPort"

Write-Host "VG Agent Dashboard"
Write-Host "  Workspace: $WorkspaceRoot (agent --chat writes traces here or under repo traces/)"
Write-Host "  API:  http://127.0.0.1:$ApiPort/api/v1/health"
Write-Host "  UI:   http://127.0.0.1:5173"
Write-Host ""
Write-Host "Starting API in a new window..."

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$RepoRoot'; `$env:VG_WORKSPACE_ROOT='$WorkspaceRoot'; `$env:VG_DASHBOARD_PORT='$ApiPort'; uv run uvicorn dashboard.api.main:app --host 127.0.0.1 --port $ApiPort --reload"
)

Push-Location "$RepoRoot\dashboard\web"
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run dev
