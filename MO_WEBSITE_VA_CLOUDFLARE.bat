@echo off
setlocal
title Huong Vi Soc Trang - Website + Cloudflare
cd /d "%~dp0"

echo ==========================================
echo   HUONG VI SOC TRANG - KHOI DONG WEBSITE
echo ==========================================
echo.

if not exist "%~dp0BAT_DAU_WEBSITE.bat" (
    echo KHONG TIM THAY BAT_DAU_WEBSITE.bat
    echo Hay dat file nay cung thu muc voi BAT_DAU_WEBSITE.bat.
    echo.
    pause
    exit /b 1
)

if not exist "%USERPROFILE%\Downloads\cloudflared-windows-amd64.exe" (
    echo KHONG TIM THAY cloudflared-windows-amd64.exe trong Downloads.
    echo Hay kiem tra ten file va thu muc Downloads.
    echo.
    pause
    exit /b 1
)

echo Dang khoi dong website...
start "Huong Vi Soc Trang Website" /min cmd /c ""%~dp0BAT_DAU_WEBSITE.bat""

echo Dang cho website khoi dong 8 giay...
timeout /t 8 /nobreak >nul

echo.
echo Dang tao duong link Cloudflare...
echo Giu cua so nay mo trong luc co giao va ban be truy cap.
echo Link trycloudflare.com se hien ben duoi neu ket noi thanh cong.
echo.

"%USERPROFILE%\Downloads\cloudflared-windows-amd64.exe" tunnel --url http://localhost:8000

echo.
echo Cloudflare da dung. Neu muon mo lai website tu xa, hay chay file nay lan nua.
pause
