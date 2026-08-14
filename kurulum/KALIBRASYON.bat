@echo off
setlocal EnableExtensions
chcp 65001 >nul
title AICAN Ortam Gurultusu Kalibrasyonu
cd /d "%~dp0.."

echo.
echo  ==============================================
echo    AICAN - ORTAM GURULTUSU KALIBRASYONU
echo  ==============================================
echo  Sergi KURULDUKTAN SONRA bir kez calistirin.
echo  Salonun kendi gurultusu olculur ve mikrofonun
echo  konusma esigi ona gore ayarlanir.
echo.
echo  ONEMLI: Sistem calisiyor olmali (BASLAT.bat) ve
echo  sergi ekrani acik olmali. Olcum sirasinda
echo  KIMSE KONUSMAMALI.
echo.

call :bul_python
if not defined PYEXE goto :python_yok

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
"%PYEXE%" -X utf8 "%~dp0kalibrasyon.py" %*
set "SONUC=%ERRORLEVEL%"
echo.
if "%SONUC%"=="0" (
  echo  Kalibrasyon tamam. Ayar kalicidir - her acilista uygulanir.
) else (
  echo  Kalibrasyon tamamlanmadi. Yukaridaki aciklamaya bakip tekrar deneyin.
)
pause
exit /b %SONUC%

:python_yok
echo  Python bulunamadi. Once kurulum\KUR.bat calistirin.
pause
exit /b 1

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
