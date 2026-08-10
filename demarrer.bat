@echo off
title MotoStockIA #TUMIKA
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Environnement virtuel introuvable. Lancez d'abord installer.bat
    pause
    exit /b 1
)

"%~dp0.venv\Scripts\python.exe" "%~dp0serve.py"

echo.
echo Le serveur s'est arrete. Vous pouvez fermer cette fenetre.
pause
