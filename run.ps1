$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir
& .\.venv\Scripts\Activate.ps1
python main.py