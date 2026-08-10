@echo off
setlocal enabledelayedexpansion
title Protection des dossiers - MotoStockIA #TUMIKA
set "APP=%~dp0"
set "SYS=NT AUTHORITY\SYSTEM"

echo ================================================
echo   Protection contre la suppression accidentelle
echo ================================================
echo.

REM ---- 1) Sauvegarde de la base de donnees ----
if exist "%APP%instance\motostock.db" (
    if not exist "%APP%sauvegardes" mkdir "%APP%sauvegardes"
    set "SAUV=%APP%sauvegardes\motostock_%DATE:~-4%%DATE:~3,2%%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%.db"
    set "SAUV=!SAUV: =0!"
    copy /Y "%APP%instance\motostock.db" "!SAUV!" >nul
    echo [OK] Sauvegarde de la base : !SAUV!
)

REM ---- 2) Protection des dossiers de code ----
REM Lecture seule + execution pour l'utilisateur (pas de modification ni suppression)
echo.
echo Protection des dossiers de l'application (lecture seule) ...
for %%D in (app templates docs migrations src static\js) do (
    if exist "%APP%%%D" (
        icacls "%APP%%%D" /reset /T /Q >nul 2>&1
        icacls "%APP%%%D" /inheritance:r /Q >nul 2>&1
        icacls "%APP%%%D" /grant:r "%USERNAME%:(OI)(CI)RX" /Q >nul 2>&1
        icacls "%APP%%%D" /grant:r "%SYS%:(OI)(CI)F" /Q >nul 2>&1
        icacls "%APP%%%D\*" /inheritance:r /grant:r "%USERNAME%:RX" /grant:r "%SYS%:F" /T /Q >nul 2>&1
        echo   [OK] %%D
    )
)

REM ---- 3) Protection de serve.py et requirements.txt ----
REM (les fichiers .bat ne sont PAS proteges)
for %%F in (serve.py requirements.txt) do (
    if exist "%APP%%%F" (
        icacls "%APP%%%F" /inheritance:r /Q >nul 2>&1
        icacls "%APP%%%F" /grant:r "%USERNAME%:RX" /Q >nul 2>&1
        icacls "%APP%%%F" /grant:r "%SYS%:F" /Q >nul 2>&1
    )
)

echo.
echo Termine. Les dossiers de l'application sont proteges (lecture seule) :
echo   - les fichiers de programme ne peuvent plus etre modifies/supprimes par erreur
echo   - une suppression recursive de l'application est refusee par ces dossiers
echo   - la base de donnees et les images restent utilisables par l'application
echo   - une sauvegarde de la base a ete creee dans le dossier sauvegardes\
echo.
echo Pour annuler la protection : executez  de_proteger_dossiers.bat
pause
