@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment was not found.
  echo Run install.bat first.
  pause
  exit /b 1
)

if not exist ".env" (
  if exist ".env.example" (
    echo Creating .env from .env.example...
    copy ".env.example" ".env" >nul
    echo Please edit .env and set DEEPSEEK_API_KEY, then run start.bat again.
    notepad ".env"
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"

echo Starting AIArxivReader at http://127.0.0.1:8765
start "" "http://127.0.0.1:8765"
python -m arxiv_reader.web --host 127.0.0.1 --port 8765

pause
