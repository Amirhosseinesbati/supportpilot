[CmdletBinding()]
param(
    [ValidateSet('small', 'full')][string]$Size = 'full',
    [switch]$Reset,
    [switch]$PrepareOnly,
    [ValidateRange(1, 65535)][int]$ApiPort = 8000,
    [ValidateRange(1, 65535)][int]$WebPort = 5173,
    [ValidateRange(0, 86400)][int]$RunSeconds = 0
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$api = Join-Path $root 'apps/api'
$web = Join-Path $root 'apps/web'
$runtime = Join-Path $root 'data/runtime'
$dbFile = Join-Path $api 'data/supportpilot.db'
$python = Join-Path $api '.venv/Scripts/python.exe'

$env:APP_MODE = 'DEMO'
$env:DATABASE_URL = 'sqlite:///./data/supportpilot.db'
$env:UPLOAD_ROOT = './data/uploads'
$env:COOKIE_SECURE = 'false'
$env:COMMERCE_ADAPTER = 'local'
$env:SUPPORT_ADAPTER = 'local'
$env:SECRET_KEY = 'local-demo-only-change-before-deployment'
$env:REFERENCE_DATE = '2026-09-27'
if (-not $env:UV_CACHE_DIR) { $env:UV_CACHE_DIR = Join-Path $root '.uv-cache' }

$uv = (Get-Command uv -ErrorAction Stop).Source
$pnpm = (Get-Command pnpm -ErrorAction Stop).Source
$node = (Get-Command node -ErrorAction Stop).Source

Push-Location $api
try {
    & $uv sync --locked --extra dev
    if ($LASTEXITCODE -ne 0) { throw 'uv sync failed' }
}
finally { Pop-Location }

if (-not (Test-Path $python)) { throw "Python environment was not created at $python" }
if (-not (Test-Path (Join-Path $root "fixtures/demo_$Size.json"))) {
    & $python (Join-Path $root 'scripts/generate_demo.py')
    if ($LASTEXITCODE -ne 0) { throw 'Demo fixture generation failed' }
}
if (-not (Test-Path (Join-Path $root 'evals/cases.jsonl'))) {
    & $python (Join-Path $root 'scripts/generate_evals.py')
    if ($LASTEXITCODE -ne 0) { throw 'Evaluation fixture generation failed' }
}

Push-Location $web
try {
    & $pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) { throw 'pnpm install failed' }
}
finally { Pop-Location }

if ($Reset -or -not (Test-Path $dbFile)) {
    Push-Location $api
    try {
        $seedArgs = @('-m', 'supportpilot.seed', '--size', $Size)
        if ($Reset) { $seedArgs += '--reset' }
        & $python @seedArgs
        if ($LASTEXITCODE -ne 0) { throw 'Demo database seed failed' }
    }
    finally { Pop-Location }
}
else {
    Write-Host "Existing DEMO database kept at $dbFile. Use -Reset to replace only synthetic workspaces."
}

if ($PrepareOnly) {
    Write-Host 'DEMO dependencies and data are ready.'
    exit 0
}

foreach ($port in @($ApiPort, $WebPort)) {
    $socket = [System.Net.Sockets.TcpClient]::new()
    try {
        $socket.Connect('127.0.0.1', $port)
        throw "Port $port is already in use; stop that service or choose -ApiPort/-WebPort."
    }
    catch [System.Net.Sockets.SocketException] {
        # A refused local connection means the port is available.
    }
    finally {
        $socket.Dispose()
    }
}
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$apiProcess = $null
$webProcess = $null
try {
    $apiProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'supportpilot.api:app', '--host', '127.0.0.1', '--port', "$ApiPort") -WorkingDirectory $api -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'api.stdout.log') -RedirectStandardError (Join-Path $runtime 'api.stderr.log')
    $webProcess = Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', "$WebPort", '--strictPort') -WorkingDirectory $web -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtime 'web.stdout.log') -RedirectStandardError (Join-Path $runtime 'web.stderr.log')

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($apiProcess.HasExited -or $webProcess.HasExited) { break }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 2
            $page = Invoke-WebRequest -Uri "http://127.0.0.1:$WebPort/" -TimeoutSec 2
            if ($health.status -eq 'ok' -and $page.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $ready) {
        Get-Content (Join-Path $runtime 'api.stderr.log') -Tail 30 -ErrorAction SilentlyContinue | Write-Host
        Get-Content (Join-Path $runtime 'web.stderr.log') -Tail 30 -ErrorAction SilentlyContinue | Write-Host
        throw 'DEMO services did not become healthy within 60 seconds'
    }
    Write-Host "SupportPilot DEMO is ready: http://127.0.0.1:$WebPort"
    Write-Host "API health: http://127.0.0.1:$ApiPort/api/health"
    Write-Host "Logs: $runtime. Press Ctrl+C to stop both services."
    $startedAt = Get-Date
    while (-not $apiProcess.HasExited -and -not $webProcess.HasExited) {
        if ($RunSeconds -gt 0 -and ((Get-Date) - $startedAt).TotalSeconds -ge $RunSeconds) {
            Write-Host 'Timed DEMO check finished; stopping both services.'
            return
        }
        Start-Sleep -Seconds 1
    }
    throw 'A DEMO service stopped; inspect the runtime logs'
}
finally {
    foreach ($process in @($apiProcess, $webProcess)) {
        if ($null -ne $process -and -not $process.HasExited) {
            try { $process.Kill($true) } catch { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
        }
    }
}
