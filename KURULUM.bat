@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo CanYouSpeak kurulumu
echo.
set "PY="
set "TEMIZLE="

rem Onceki kurulum Python 3.12 ile yapildiysa sanal ortami yeniden kurma
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" 2>nul && goto paketler
  echo Onceki kurulum yarim kalmis ya da farkli bir Python surumuyle yapilmis, yeniden kuruluyor...
  set "TEMIZLE=--clear"
)

call :python_bul
if defined PY goto ortam

rem Python 3.12 yok: winget ile kullanici hesabina kur (yonetici izni gerekmez)
echo Python 3.12 bulunamadi. Simdi otomatik kuruluyor, birkac dakika surebilir...
where winget >nul 2>nul || goto elle_kur
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :python_bul
if defined PY goto ortam

:elle_kur
echo.
echo Python 3.12 otomatik kurulamadi. Lutfen elle kurun:
echo   1. https://www.python.org/downloads/release/python-31210/ sayfasindaki "Files"
echo      tablosundan "Windows installer (64-bit)" dosyasini indirip calistirin.
echo   2. Ilk ekranda en alttaki "Add python.exe to PATH" kutusunu isaretleyin.
echo   3. Kurulum bitince bu dosyayi (KURULUM.bat) yeniden calistirin.
pause
exit /b 1

:ortam
echo Python bulundu: %PY%
"%PY%" -m venv %TEMIZLE% .venv
if errorlevel 1 goto hata

:paketler
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

rem PY: bulunan Python 3.12'nin yolu. Yeni kurulan Python bu pencerenin PATH'inde henuz
rem gorunmez, bu yuzden once bilinen kurulum klasorlerine bakilir.
:python_bul
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\python.exe" "%ProgramFiles%\Python312\python.exe") do (
  if not defined PY if exist %%P set "PY=%%~P"
)
if defined PY exit /b 0
for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%P"
if defined PY exit /b 0
rem Microsoft Store'un sahte python.exe'si stdout'a bir sey yazmaz, o yuzden yanlislikla secilmez
for /f "delims=" %%P in ('python -c "import sys; print(sys.executable if sys.version_info[:2] == (3, 12) else '')" 2^>nul') do set "PY=%%P"
exit /b 0
