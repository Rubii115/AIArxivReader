@echo off
setlocal
cd /d "%~dp0"

echo [AIArxivReader] Installing local environment...

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Please install Python 3.11+ and try again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
) else (
  echo Virtual environment already exists.
)

call ".venv\Scripts\activate.bat"

echo Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

echo Installing AIArxivReader...
python -m pip install -e .
if errorlevel 1 (
  echo Failed to install project.
  pause
  exit /b 1
)

if not exist "config.toml" (
  echo Creating config.toml from config.example.toml...
  copy "config.example.toml" "config.toml" >nul
) else (
  echo config.toml already exists.
)

if not exist ".env" (
  echo Creating .env from .env.example...
  copy ".env.example" ".env" >nul
) else (
  echo .env already exists.
)

echo.
echo Install complete.
echo Next step: edit .env and set DEEPSEEK_API_KEY.
echo You can run start.bat after setting the key.
echo.
pause
