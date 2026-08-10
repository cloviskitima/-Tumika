# Cree les raccourcis Bureau + Menu Demarrer pour MotoStockIA.
# Le script doit etre place a la racine de l'application :
# il utilise son propre dossier ($PSScriptRoot) comme chemin de l'app.
$ErrorActionPreference = 'Stop'

$app = $PSScriptRoot
if ([string]::IsNullOrEmpty($app)) { $app = (Get-Location).Path }
$app = $app.TrimEnd('\')

$cible = Join-Path $app 'demarrer.bat'
$ico = Join-Path $app 'assets\motostock.ico'

if (-not (Test-Path -LiteralPath $cible)) {
    Write-Host "ERREUR : demarrer.bat introuvable dans $app" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $ico)) { $ico = '' }

$ws = New-Object -ComObject WScript.Shell

# Bureau
$dsk = $ws.CreateShortcut((Join-Path $ws.SpecialFolders.Item('Desktop') 'MotoStockIA.lnk'))
$dsk.TargetPath = $cible
$dsk.WorkingDirectory = $app
$dsk.IconLocation = $ico
$dsk.Description = 'MotoStockIA #TUMIKA'
$dsk.Save()

# Menu Demarrer
$smDir = Join-Path $ws.SpecialFolders.Item('Programs') 'MotoStockIA'
New-Item -ItemType Directory -Force -Path $smDir | Out-Null
$sm = $ws.CreateShortcut((Join-Path $smDir 'MotoStockIA.lnk'))
$sm.TargetPath = $cible
$sm.WorkingDirectory = $app
$sm.IconLocation = $ico
$sm.Description = 'MotoStockIA #TUMIKA'
$sm.Save()

Write-Host 'Raccourcis crees avec succes.'
