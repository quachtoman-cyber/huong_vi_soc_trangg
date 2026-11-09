@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 server.py
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    python server.py
  ) else (
    echo Chua tim thay Python. Hay cai Python 3 tu https://www.python.org/downloads/
    echo Khi cai dat, nho chon Add Python to PATH.
    pause
  )
)
pause
