param(
    [string]$HostAddress = "0.0.0.0",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [switch]$Bootstrap
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

function Get-LocalIPv4 {
    try {
        $route = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -ErrorAction Stop |
            Where-Object { $_.NextHop -ne "0.0.0.0" } |
            Sort-Object RouteMetric, InterfaceMetric |
            Select-Object -First 1
        if ($route) {
            $address = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction Stop |
                Where-Object { $_.IPAddress -notlike "169.254.*" } |
                Select-Object -ExpandProperty IPAddress -First 1
            if ($address) { return $address }
        }
    } catch {
        # Older Windows versions may not expose the NetTCPIP cmdlets.
    }

    try {
        return [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
            Where-Object {
                $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
                $_.IPAddressToString -notlike "127.*" -and
                $_.IPAddressToString -notlike "169.254.*"
            } |
            Select-Object -ExpandProperty IPAddressToString -First 1
    } catch {
        return $null
    }
}

function New-ProjectVenv {
    Write-Host "[SETUP] Creating the project virtual environment (.venv) ..." -ForegroundColor Yellow
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv ".venv"
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv ".venv"
    } else {
        throw "Python was not found. Install Python 3.11 or later and try again."
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        throw "Failed to create the Python virtual environment."
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (-not $Bootstrap) {
        throw ".venv was not found. Use start.bat for first launch or follow RUN_GUIDE.md."
    }
    New-ProjectVenv
}

if ($Bootstrap) {
    & $VenvPython -c "import fastapi, uvicorn, paramiko, yaml, pydantic, multipart, playwright, openpyxl" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[SETUP] Installing missing project dependencies ..." -ForegroundColor Yellow
        & $VenvPython -m pip install -r (Join-Path $ProjectDir "requirements.txt")
        if ($LASTEXITCODE -ne 0) { throw "Failed to install project dependencies." }
    }
}

$LocalIP = Get-LocalIPv4
if (-not $LocalIP) { $LocalIP = "127.0.0.1" }
$LocalUrl = "http://127.0.0.1:$Port"
$LanUrl = "http://${LocalIP}:$Port"

# The screenshot worker runs on this machine, so loopback is the most reliable callback URL.
$env:RTR_PUBLIC_BASE_URL = $LocalUrl

Clear-Host
Write-Host "============================================================" -ForegroundColor DarkGreen
Write-Host " Remote Test Runner" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor DarkGreen
Write-Host ""
Write-Host " Starting the service. Runtime logs will remain in this window." -ForegroundColor White
Write-Host " Local URL: $LocalUrl" -ForegroundColor Cyan
Write-Host " LAN URL:   $LanUrl" -ForegroundColor Cyan
Write-Host " Listening: ${HostAddress}:$Port" -ForegroundColor DarkGray
Write-Host ""
Write-Host " Keep this window open. Press Ctrl+C to stop the service." -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGreen
Write-Host ""

& $VenvPython -m uvicorn backend.main:app --host $HostAddress --port $Port --log-level info
$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] The service exited with code $ExitCode." -ForegroundColor Red
}
exit $ExitCode
