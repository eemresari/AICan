@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AICAN Sergi
cd /d "%~dp0"

call :bul_python
if not defined PYEXE goto :python_yok

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

rem Ollama calisiyor mu? Calismiyorsa arka planda baslat.
rem (urllib: pip paketlerine bagimli olmayan saf kontrol)
"%PYEXE%" -c "import urllib.request;urllib.request.urlopen('http://localhost:11434',timeout=2)" >nul 2>&1
if not errorlevel 1 goto :ollama_hazir

call :bul_ollama
if not defined OLLAMAEXE goto :ollama_yok
echo Ollama baslatiliyor...
start "" /min "%OLLAMAEXE%" serve
timeout /t 6 /nobreak >nul
goto :ollama_hazir

:ollama_yok
echo UYARI: Ollama bulunamadi - LLM ozellikleri calismayabilir.
echo Kurulum icin: kurulum\KUR.bat

:ollama_hazir
echo AICAN baslatiliyor... Tarayici sekmeleri (sergi + kontrol) acilacak.
echo Kapatmak icin bu pencereyi kapatin.
"%PYEXE%" run_web.py
pause
exit /b 0

:python_yok
echo Python bulunamadi. Once kurulum\KUR.bat calistirin.
pause
exit /b 1

:bul_python
set "PYEXE="
rem Depodaki .venv HER ZAMAN once: bagimliliklar (flask, faster-whisper, edge-tts)
rem orada kurulu. Sistem Python'i secilirse run_web.py "No module named flask"
rem ile aninda oluyordu (2026-09-13).
if exist "%~dp0.venv\Scripts\python.exe" set "PYEXE=%~dp0.venv\Scripts\python.exe"
if defined PYEXE goto :eof
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

:bul_ollama
set "OLLAMAEXE="
for /f "delims=" %%p in ('where ollama 2^>nul') do if not defined OLLAMAEXE set "OLLAMAEXE=%%p"
if defined OLLAMAEXE goto :eof
for %%d in ("%LocalAppData%\Programs\Ollama\ollama.exe" "C:\Program Files\Ollama\ollama.exe") do (
  if not defined OLLAMAEXE if exist "%%~d" set "OLLAMAEXE=%%~d"
)
goto :eof
