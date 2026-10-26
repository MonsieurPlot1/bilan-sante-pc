@echo off
rem Fabrique dist\BilanSantePC\BilanSantePC.exe avec PyInstaller, puis son installateur avec Inno Setup :
rem dist\BilanSantePC-Installation-vX.Y.Z.exe (version lue dans config.py).
setlocal
cd /d "%~dp0"

rem Python du venv du projet s'il existe, sinon celui du PATH.
set PYTHON=python
if exist .venv\Scripts\python.exe set PYTHON=.venv\Scripts\python.exe

rem Icone : assets\icon.ico, celle du .exe, et copiee a cote pour la fenetre (ui\theme.py).
set ICONE=
if exist assets\icon.ico set ICONE=--icon assets\icon.ico --add-data "assets\icon.ico;assets"

%PYTHON% -m PyInstaller --noconfirm --clean --onedir --windowed --name BilanSantePC %ICONE% main.py
if errorlevel 1 (
    echo La compilation a echoue.
    exit /b 1
)
echo Termine : dist\BilanSantePC\BilanSantePC.exe

rem Inno Setup 6 (winget install JRSoftware.InnoSetup), installe pour l'utilisateur ou pour tous.
set ISCC=
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not defined ISCC (
    echo Inno Setup introuvable : pas d'installateur. Installe-le avec : winget install JRSoftware.InnoSetup
    exit /b 1
)
for /f %%v in ('%PYTHON% -c "import config; print(config.VERSION)"') do set VERSION=%%v
"%ISCC%" /Q /DVersion=%VERSION% installateur.iss
if errorlevel 1 (
    echo La fabrication de l'installateur a echoue.
    exit /b 1
)
echo Termine : dist\BilanSantePC-Installation-v%VERSION%.exe
