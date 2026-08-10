@echo off
title Annulation de la protection - MotoStockIA #TUMIKA
setlocal
set "APP=%~dp0"

echo ================================================
echo   Annulation de la protection des dossiers
echo ================================================
echo.

for %%D in (app templates docs migrations src static\js) do (
    if exist "%APP%%%D" (
        icacls "%APP%%%D" /reset /T /Q
        echo   [OK] %%D
    )
)

for %%F in (serve.py requirements.txt) do (
    if exist "%APP%%%F" (
        icacls "%APP%%%F" /reset /Q
    )
)

echo.
echo Protection annulee. Les dossiers sont de nouveau supprimables.
pause
