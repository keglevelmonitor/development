@echo off
SETLOCAL EnableDelayedExpansion

TITLE KegLevel Monitor Installer

echo ==========================================
echo      KegLevel Monitor Windows Installer
echo ==========================================
echo.

REM --- 1. Set Paths ---
REM %~dp0 expands to the drive and path of this script
SET "PROJECT_ROOT=%~dp0"
REM Remove trailing backslash if present
IF "%PROJECT_ROOT:~-1%"=="\" SET "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

SET "VENV_PATH=%PROJECT_ROOT%\venv"
SET "DATA_DIR=%USERPROFILE%\keglevel-data"
SET "MAIN_SCRIPT=%PROJECT_ROOT%\src\main.py"
REM Note: Windows shortcuts prefer .ico files, but .png often works or defaults to Python icon
SET "ICON_FILE=%PROJECT_ROOT%\src\assets\beer-keg.png"

echo Target Directory: %PROJECT_ROOT%
echo Data Directory:   %DATA_DIR%
echo.

REM --- 2. Check for Python ---
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python is not detected!
    echo Please install Python from python.org and ensure "Add Python to PATH" is checked.
    pause
    exit /b 1
)

REM --- 3. Create Data Directory ---
if not exist "%DATA_DIR%" (
    echo [INFO] Creating data directory...
    mkdir "%DATA_DIR%"
) else (
    echo [INFO] Data directory already exists.
)

REM --- 4. Create Virtual Environment ---
echo [INFO] Checking virtual environment...
if exist "%VENV_PATH%" (
    echo [INFO] Removing existing venv to ensure clean install...
    rmdir /s /q "%VENV_PATH%"
)

echo [INFO] Creating new virtual environment...
python -m venv "%VENV_PATH%"
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

REM --- 5. Install Dependencies ---
echo [INFO] Installing dependencies...
echo.
echo NOTE: We are skipping 'requirements.txt' because it contains Raspberry Pi specific
echo drivers (rpi-lgpio) that are incompatible with Windows.
echo The app will run in 'Simulation Mode' using standard Python libraries.
echo.

REM Upgrade pip just in case
"%VENV_PATH%\Scripts\python.exe" -m pip install --upgrade pip >nul

REM If you add cross-platform libraries later (like Pillow or requests), install them here:
REM "%VENV_PATH%\Scripts\pip.exe" install requests

REM --- 6. Create Desktop Shortcut ---
echo [INFO] Creating Desktop Shortcut...

set "SHORTCUT_PATH=%USERPROFILE%\Desktop\KegLevel Monitor.lnk"
set "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"

REM Use PowerShell to create the shortcut programmatically
set "PS_CMD=$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT_PATH%');"
set "PS_CMD=%PS_CMD% $s.TargetPath='%PYTHON_EXE%'; $s.Arguments='\"%MAIN_SCRIPT%\"';"
set "PS_CMD=%PS_CMD% $s.WorkingDirectory='%PROJECT_ROOT%'; $s.IconLocation='%ICON_FILE%'; $s.Save()"

powershell -Command "%PS_CMD%"

echo.
echo ==========================================
echo        Installation Complete!
echo ==========================================
echo You can now launch the app from the shortcut on your Desktop.
echo.
pause
