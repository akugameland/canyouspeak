@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo CanYouSpeak kurulumu (Python 3.12 gerekir)...
python -m venv .venv
if errorlevel 1 goto hata
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto hata
".venv\Scripts\python.exe" modelleri_indir.py
if errorlevel 1 goto hata
echo.
echo Kurulum tamam. BASLAT.bat ile acin.
pause
exit /b 0
:hata
echo.
echo Kurulum basarisiz oldu. Yukaridaki hata mesajina bakin.
pause
exit /b 1
