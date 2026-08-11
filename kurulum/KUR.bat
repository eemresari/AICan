@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AICAN Kurulum
cd /d "%~dp0.."

echo.
echo  ==============================================
echo    AICAN SERGI KURULUMU  (temiz PC icin)
echo  ==============================================
echo  Bu betik: ekran kartini tespit eder, Python + bagimliliklar
echo  + Ollama + dil modeli + Whisper + cevrimdisi sesi kurar,
echo  karta uygun profili secer, kisayol olusturur ve sonunda
echo  saglik kontrolu calistirir. Internet gerekir.
echo.
echo  Proje klasoru henuz makinede yoksa once SIFIRDAN_KUR.ps1 kullan.
echo.

call :bul_python
if defined PYEXE goto :python_ok

echo  Python bulunamadi - winget ile kuruluyor (birkac dakika surebilir)...
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
call :bul_python
if defined PYEXE goto :python_ok
echo.
echo  Python kuruldu ama bu pencereden henuz gorunmuyor.
echo  Bu pencereyi KAPATIP kurulum\KUR.bat dosyasini TEKRAR calistirin.
echo  (winget de basarisiz olduysa elle kurun: https://www.python.org/downloads/
echo   kurulum ekraninda "Add python.exe to PATH" kutusunu isaretleyin)
pause
exit /b 1

:python_ok
echo  Python bulundu: %PYEXE%
echo.
"%PYEXE%" -X utf8 "%~dp0kur.py" %*
set "SONUC=%ERRORLEVEL%"
echo.
if not "%SONUC%"=="0" echo  Kurulum HATALI bitti - yukaridaki mesajlara bakin.
pause
exit /b %SONUC%

:bul_python
set "PYEXE="
for /f "delims=" %%p in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PYEXE set "PYEXE=%%p"
if defined PYEXE if not exist "%PYEXE%" set "PYEXE="
if defined PYEXE goto :eof
for /f "delims=" %%p in ('python -c "import sys;print(sys.executable)" 2^>nul') do if not defined PYEXE set "PYEXE=%%p"
if defined PYEXE if not exist "%PYEXE%" set "PYEXE="
if defined PYEXE goto :eof
for %%d in ("%LocalAppData%\Programs\Python\Python314" "%LocalAppData%\Programs\Python\Python313" "%LocalAppData%\Programs\Python\Python312" "C:\Program Files\Python314" "C:\Program Files\Python313" "C:\Program Files\Python312") do (
  if not defined PYEXE if exist "%%~d\python.exe" set "PYEXE=%%~d\python.exe"
)
goto :eof
