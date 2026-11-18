[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $env:PATH = "$scriptDir\.venv\Scripts;$env:PATH"
    & $venvPython main.py @ScriptArgs
} else {
    Write-Host "[INFO] Virtual environment (.venv) not found. Using system python..." -ForegroundColor Yellow
    python main.py @ScriptArgs
}
