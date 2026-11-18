@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo [INFO] Virtual environment .venv not found. Attempting system Python...
)

python main.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %ERRORLEVEL%.
    pause
)
endlocal
