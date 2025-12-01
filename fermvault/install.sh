#!/bin/bash
# install.sh
# Installation script for FermVault application.

# Stop on any error to prevent partial installs
set -e

echo "=========================================="
echo "   FermVault Installer"
echo "=========================================="

# --- 1. Define Variables ---
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_EXEC="python3"
VENV_DIR="$PROJECT_DIR/venv"
VENV_PYTHON_EXEC="$VENV_DIR/bin/python"
DESKTOP_FILE_TEMPLATE="$PROJECT_DIR/fermvault.desktop"
INSTALL_LOCATION="$HOME/.local/share/applications/fermvault.desktop"
DATA_DIR="$HOME/fermvault-data"

echo "Project path: $PROJECT_DIR"

# --- 2. Install System Dependencies (Requires Sudo) ---
echo ""
echo "--- [Step 1/5] Checking System Dependencies ---"
echo "You may be asked for your password to install system packages."

# We use sudo explicitly here. The user runs the script as 'pi', 
# but this specific command runs as root.
sudo apt-get update
sudo apt-get install -y python3-tk python3-dev swig python3-venv liblgpio-dev

# --- 3. Setup Python Environment (Clean Install) ---
echo ""
echo "--- [Step 2/5] Setting up Virtual Environment ---"

# CLEANUP: Delete existing venv to ensure a clean slate
if [ -d "$VENV_DIR" ]; then
    echo "Removing old virtual environment for a clean install..."
    rm -rf "$VENV_DIR"
fi

echo "Creating new Python virtual environment at $VENV_DIR..."
$PYTHON_EXEC -m venv "$VENV_DIR"

if [ $? -ne 0 ]; then
    echo "[FATAL ERROR] Failed to create virtual environment."
    exit 1
fi

# --- 4. Install Python Libraries ---
echo ""
echo "--- [Step 3/5] Installing Python Libraries ---"

# Verify requirements.txt exists
if [ ! -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "[FATAL ERROR] requirements.txt not found in $PROJECT_DIR."
    exit 1
fi

# Install using the pip INSIDE the virtual environment
"$VENV_PYTHON_EXEC" -m pip install --upgrade pip
"$VENV_PYTHON_EXEC" -m pip install -r "$PROJECT_DIR/requirements.txt"

if [ $? -ne 0 ]; then
    echo "[FATAL ERROR] Dependency installation failed."
    exit 1
fi

# --- 5. Create User Data Directory ---
echo ""
echo "--- [Step 4/5] Configuring Data Directory ---"
if [ ! -d "$DATA_DIR" ]; then
    echo "Creating user data directory: $DATA_DIR"
    mkdir -p "$DATA_DIR"
    chmod 700 "$DATA_DIR"
else
    echo "Data directory already exists ($DATA_DIR). Skipping."
fi

# --- 6. Install Desktop Shortcut ---
echo ""
echo "--- [Step 5/5] Installing Desktop Shortcut ---"

if [ -f "$DESKTOP_FILE_TEMPLATE" ]; then
    # 4a. Define paths
    # Note: We point to the MAIN.PY in src, but we use the VENV python to execute it.
    # This ensures the app always uses the isolated libraries.
    EXEC_CMD="$VENV_PYTHON_EXEC $PROJECT_DIR/src/main.py"
    ICON_PATH="$PROJECT_DIR/src/assets/fermenter.png"
    
    # 1. Copy to temp
    cp "$DESKTOP_FILE_TEMPLATE" /tmp/fermvault_temp.desktop
    
    # 2. Update Exec path to use VENV python
    sed -i "s|Exec=PLACEHOLDER_EXEC_PATH|Exec=$EXEC_CMD|g" /tmp/fermvault_temp.desktop
    
    # 3. Update Path (working directory)
    sed -i "s|Path=PLACEHOLDER_PATH|Path=$PROJECT_DIR/src|g" /tmp/fermvault_temp.desktop

    # 4. Update Icon path
    sed -i "s|Icon=PLACEHOLDER_ICON_PATH|Icon=$ICON_PATH|g" /tmp/fermvault_temp.desktop
    
    # 5. Move to user applications folder
    mkdir -p "$HOME/.local/share/applications"
    mv /tmp/fermvault_temp.desktop "$INSTALL_LOCATION"
    
    # 6. Make executable
    chmod +x "$INSTALL_LOCATION"
    
    echo "Shortcut installed to: $INSTALL_LOCATION"
else
    echo "[WARNING] fermvault.desktop template not found. Skipping shortcut."
fi

echo ""
echo "==========================================================================="
echo "   Installation Complete!"
echo ""
echo "   At the Applications menu, select Other, Fermentation Vault to run the app."
echo ""
echo "   You may need to reboot your RPi to refresh the menu."
echo "==========================================================================="

