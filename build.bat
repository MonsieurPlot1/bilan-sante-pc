@echo off
rem Fabrique dist\BilanSantePC\BilanSantePC.exe avec PyInstaller.
setlocal
cd /d "%~dp0"

rem Python du venv du projet s'il existe, sinon celui du PATH.
set PYTHON=python
if exist .venv\Scripts\python.exe set PYTHON=.venv\Scripts\python.exe

rem Icone : assets\icon.ico, celle du .exe, et copiee a cote pour la fenetre (ui\theme.py).
set ICONE=
if exist assets\icon.ico set ICONE=--icon assets\icon.ico --add-data "assets\icon.ico;assets"

rem Police Inter (assets\polices, licence OFL) : copiee telle quelle, ui\theme.py la charge au lancement.
set POLICES=--add-data "assets\polices;assets\polices"

%PYTHON% -m PyInstaller --noconfirm --clean --onedir --windowed --name BilanSantePC %ICONE% %POLICES% main.py
if errorlevel 1 (
    echo La compilation a echoue.
    exit /b 1
)
echo Termine : dist\BilanSantePC\BilanSantePC.exe
