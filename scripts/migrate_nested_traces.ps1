# Move JSONL from workspace/workspace/traces/ (legacy Docker cwd bug) into repo traces/.
# Safe to re-run: skips files already present at destination with same size.
param(
    [string]$NestedDir = "workspace/workspace/traces",
    [string]$DestDir = "traces"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path $NestedDir)) {
    Write-Host "Nothing to migrate ($NestedDir missing)."
    exit 0
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
$moved = 0
$skipped = 0
$removedDup = 0

Get-ChildItem "$NestedDir/*.jsonl" | ForEach-Object {
    $dest = Join-Path $DestDir $_.Name
    if (Test-Path $dest) {
        $existing = Get-Item $dest
        if ($existing.Length -eq $_.Length) {
            Remove-Item $_.FullName -Force
            $removedDup++
            return
        }
        Write-Warning "Skip $($_.Name): destination exists with different size."
        $skipped++
        return
    }
    Move-Item $_.FullName $dest
    $moved++
}

Write-Host "migrate_nested_traces: moved=$moved removed_duplicate=$removedDup skipped=$skipped"
if ((Get-ChildItem $NestedDir -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
    Write-Host "Nested dir empty of traces; you may remove $NestedDir manually."
}
