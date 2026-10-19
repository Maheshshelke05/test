# Starts the whole CampusBite stack locally in separate windows (Windows / PowerShell).
#   .\start-local.ps1          start everything
#   .\start-local.ps1 -Reseed  wipe and reseed the demo database first
param([switch]$Reseed)

$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creating backend virtualenv..."
    python -m venv (Join-Path $root "backend\.venv")
    & $py -m pip install -r (Join-Path $root "backend\requirements.txt")
}
if ($Reseed -or -not (Test-Path (Join-Path $root "backend\campusbite.db"))) {
    Push-Location (Join-Path $root "backend"); & $py seed.py; Pop-Location
}
foreach ($app in "student", "kitchen", "admin") {
    if (-not (Test-Path (Join-Path $root "apps\$app\node_modules"))) {
        Push-Location (Join-Path $root "apps\$app"); npm install; Pop-Location
    }
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; & '$py' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\admin'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\student'; npx expo start --port 8081"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\apps\kitchen'; npx expo start --port 8082"

Write-Host ""
Write-Host "API        http://localhost:8000/docs"
Write-Host "Admin      http://localhost:3000   (9000000000 / OTP 123456)"
Write-Host "Student    press 'w' in its Expo window, or scan the QR with Expo Go (9800000001)"
Write-Host "Kitchen    press 'w' in its Expo window, or scan the QR with Expo Go (9100000001 owner)"
