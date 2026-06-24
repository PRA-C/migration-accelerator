# Start Migration Accelerator dev stack (API + React UI)
$root = Split-Path -Parent $PSScriptRoot

# Stop stale API on :8000 so code changes (health ui_fix, SSE fixes) actually load.
$existing = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $existing) {
  if ($procId) {
    Write-Host "Stopping stale API process PID $procId on port 8000 ..."
    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
  }
}
Start-Sleep -Seconds 1

Write-Host "Starting API on http://127.0.0.1:8000 ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; `$env:API_RELOAD='true'; uv run python -m api"

Start-Sleep -Seconds 2

Write-Host "Starting UI on http://127.0.0.1:5173 ..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev -- --host 127.0.0.1"

Write-Host "Done. Open http://127.0.0.1:5173"
