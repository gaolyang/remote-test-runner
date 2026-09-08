param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    & $VenvPython -m uvicorn backend.main:app --host $HostAddress --port $Port
} else {
    python -m uvicorn backend.main:app --host $HostAddress --port $Port
}
