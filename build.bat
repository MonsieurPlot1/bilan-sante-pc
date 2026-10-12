@echo off
rem Fabrique dist\BilanSantePC\BilanSantePC.exe avec PyInstaller.
setlocal
cd /d "%~dp0"

rem Python du venv du projet s'il existe, sinon celui du PATH.
set PYTHON=python
if exist .venv\Scripts\python.exe set PYTHON=.venv\Scripts\python.exe

rem Icone facultative : assets\icon.ico si elle existe.
set ICONE=
if exist assets\icon.ico set ICONE=--icon assets\icon.ico

%PYTHON% -m PyInstaller --noconfirm --clean --onedir --windowed --name BilanSantePC %ICONE% main.py
if errorlevel 1 (
    echo La compilation a echoue.
    exit /b 1
)
echo Termine : dist\BilanSantePC\BilanSantePC.exe
