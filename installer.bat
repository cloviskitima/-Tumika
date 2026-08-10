@echo off
setlocal enabledelayedexpansion
title Installation MotoStockIA #TUMIKA
cd /d "%~dp0"
set "APP=%~dp0"

echo ================================================
echo    Installation MotoStockIA #TUMIKA
echo ================================================
echo.

REM -----------------------------------------------
REM  1) Verifier / installer Python 3.12
REM -----------------------------------------------
set "PY="
where python >nul 2>&1
if not errorlevel 1 set "PY=python"
if defined PY goto pyok
py -3 --version >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if defined PY goto pyok

echo [1/5] Python introuvable : installation de Python 3.12 ...
if not exist "%APP%setup\python\python-3.12.3-amd64.exe" (
    echo ERREUR : installateur Python absent de setup\python
    echo Telechargez python-3.12.3-amd64.exe et placez-le dans setup\python
    pause
    exit /b 1
)

start /wait "" "%APP%setup\python\python-3.12.3-amd64.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1

set "PYPATH=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set /a tries=0
:waitpy
if exist "%PYPATH%" set "PY=%PYPATH%"
if not defined PY (
    set /a tries+=1
    if !tries! lss 90 ( ping -n 2 127.0.0.1 >nul )
    if !tries! lss 90 goto waitpy
)

:pyok
if not defined PY (
    echo ERREUR : Python n'a pas pu etre detecte. Installez-le manuellement depuis python.org
    pause
    exit /b 1
)

echo Python detecte :
%PY% --version
echo.

REM -----------------------------------------------
REM  2) Environnement virtuel
REM -----------------------------------------------
echo [2/5] Creation de l'environnement virtuel (.venv) ...
if not exist "%APP%.venv" (
    %PY% -m venv "%APP%.venv"
)
set "PYV=%APP%.venv\Scripts\python.exe"
if not exist "%PYV%" (
    echo ERREUR : impossible de creer l'environnement virtuel.
    pause
    exit /b 1
)
echo.

REM -----------------------------------------------
REM  3) Dependances (requirements.txt)
REM -----------------------------------------------
echo [3/5] Installation des dependances (peut prendre plusieurs minutes) ...
"%PYV%" -m pip install --upgrade pip
"%PYV%" -m pip install -r "%APP%requirements.txt"
echo.

REM -----------------------------------------------
REM  4) Tesseract OCR (optionnel)
REM -----------------------------------------------
echo [4/5] Verification de Tesseract OCR (optionnel) ...
where tesseract >nul 2>&1
if errorlevel 1 (
    where winget >nul 2>&1
    if not errorlevel 1 (
        echo Installation de Tesseract OCR via winget (necessite Internet) ...
        winget install --id UB-Mannheim.TesseractOCR -e --accept-package-agreements --accept-source-agreements >nul 2>&1
    ) else (
        echo Tesseract non installe : l'OCR restera indisponible (le reste fonctionne).
    )
)
echo.

REM -----------------------------------------------
REM  5) Raccourcis Bureau + Menu Demarrer
REM -----------------------------------------------
echo [5/5] Creation des raccourcis (Bureau + Menu Demarrer) ...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $ws = New-Object -ComObject WScript.Shell; $app = (Get-Location).Path; $ico = Join-Path $app 'assets\motostock.ico'; $cible = Join-Path $app 'demarrer.bat'; $dsk = $ws.CreateShortcut((Join-Path $ws.SpecialFolders('Desktop') 'MotoStockIA.lnk')); $dsk.TargetPath = $cible; $dsk.WorkingDirectory = $app; $dsk.IconLocation = $ico; $dsk.Description = 'MotoStockIA #TUMIKA'; $dsk.Save(); $smDir = Join-Path $ws.SpecialFolders('Programs') 'MotoStockIA'; New-Item -ItemType Directory -Force -Path $smDir | Out-Null; $sm = $ws.CreateShortcut((Join-Path $smDir 'MotoStockIA.lnk')); $sm.TargetPath = $cible; $sm.WorkingDirectory = $app; $sm.IconLocation = $ico; $sm.Description = 'MotoStockIA #TUMIKA'; $sm.Save(); Write-Host 'Raccourcis crees avec succes.'"

echo.
echo ================================================
echo    Installation terminee !
echo.
echo    - Raccourci sur le Bureau  : MotoStockIA
echo    - Raccourci Menu Demarrer  : MotoStockIA
echo    - Pour lancer : double-cliquez sur le raccourci
echo      (demarre le serveur et ouvre le navigateur)
echo ================================================
echo.
choice /c ON /n /m "   Proteger les dossiers contre la suppression accidentelle ? (O=Oui / N=Non) : "
if errorlevel 2 goto fin
call "%APP%proteger_dossiers.bat"
:fin
echo.
echo Pour arreter l'application plus tard : fermez simplement la fenetre du serveur.
pause
