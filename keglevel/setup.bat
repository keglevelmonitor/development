@echo off
SETLOCAL EnableDelayedExpansion

TITLE KegLevel Monitor Auto-Installer

REM --- 1. Configuration ---
SET "TARGET_DIR=%USERPROFILE%\keglevel"
SET "DATA_DIR=%USERPROFILE%\keglevel-data"
SET "REPO_URL=https://github.com/keglevelmonitor/keglevel.git"

REM Get the directory where this script is currently running
SET "CURRENT_SCRIPT_DIR=%~dp0"
REM Remove trailing backslash for comparison
IF "%CURRENT_SCRIPT_DIR:~-1%"=="\" SET "CURRENT_SCRIPT_DIR=%CURRENT_SCRIPT_DIR:~0,-1%"

echo ========================================
echo    KegLevel Monitor Windows Setup
echo ========================================
echo.

REM --- 2. Check if running from INSIDE the target folder ---
IF /I "%CURRENT_SCRIPT_DIR%"=="%TARGET_DIR%" (
    echo [INFO] You are running this script from inside the installation folder.
    echo [INFO] "Fresh Install" -Wipe- mode is disabled to prevent file lock errors.
    echo.
    echo Launching internal configuration -Update/Repair mode-...
    echo.
    if exist "install.bat" (
        call install.bat
    ) else (
        echo [ERROR] install.bat not found!
    )
    exit /b 0
)

REM --- 3. Standard "Bootstrapper" Mode (Running from Desktop/Temp) ---

REM Check Prerequisites
git --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL ERROR] Git is not installed.
    echo Windows requires Git to download the repository.
    echo Please install "Git for Windows": https://git-scm.com/download/win
    pause
    exit /b 1
)

python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [CRITICAL ERROR] Python is not installed.
    echo Please install Python and check "Add Python to PATH".
    pause
    exit /b 1
)

REM Check for Existing Installation
IF EXIST "%TARGET_DIR%" (
    echo Existing installation detected at:
    echo  %TARGET_DIR%
    echo.
    echo How would you like to proceed?
    echo  [1] Reinstall APP only (Keeps data/settings, updates code)
    echo  [2] Fresh Install (DELETES ALL DATA and APP)
    echo  [3] Cancel
    echo.
    set /p "CHOICE=Enter selection (1-3): "

    IF "!CHOICE!"=="1" (
        echo Removing existing application files...
        rmdir /s /q "%TARGET_DIR%"
    ) ELSE IF "!CHOICE!"=="2" (
        echo.
        echo WARNING: This will delete your settings and data in:
        echo %DATA_DIR%
        echo.
        set /p "CONFIRM=Are you sure? Type YES to confirm: "
        IF /I "!CONFIRM!"=="YES" (
            echo Removing application...
            rmdir /s /q "%TARGET_DIR%"
            echo Removing data...
            rmdir /s /q "%DATA_DIR%"
        ) ELSE (
            echo Cancelled.
            pause
            exit /b 0
        )
    ) ELSE (
        echo Cancelled.
        pause
        exit /b 0
    )
)

REM Clone Repository
echo.
echo --- Downloading KegLevel Monitor... ---
git clone %REPO_URL% "%TARGET_DIR%"

IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to download repository.
    pause
    exit /b 1
)

REM Handover to Internal Installer
echo.
echo --- Launching Configuration... ---
cd /d "%TARGET_DIR%"

IF EXIST "install.bat" (
    call install.bat
) ELSE (
    echo [ERROR] install.bat not found in the downloaded repository!
    pause
    exit /b 1
)
