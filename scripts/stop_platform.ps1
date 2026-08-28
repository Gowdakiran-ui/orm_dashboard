$pidFile = Join-Path $PSScriptRoot ".platform_pids.json"
if (Test-Path $pidFile) {
    try {
        $tracked = Get-Content $pidFile -Raw | ConvertFrom-Json
        foreach ($prop in $tracked.PSObject.Properties) {
            $procId = $prop.Value
            if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
                Write-Host "Stopping $($prop.Name) (PID $procId)..."
                taskkill /F /T /PID $procId *>$null
            }
        }
    } catch {
    } finally {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }
}
Get-NetTCPConnection -LocalPort 8000,3000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
