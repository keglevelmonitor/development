#!/bin/bash
# update.sh
# Handles pulling code AND dependency updates for FermVault.
# --- MODIFIED TO USE VIRTUAL ENVIRONMENT ---

# --- 1. Define Variables ---
# Get the full path to the directory this script is in (the project root)
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- ADDED: Define paths for the virtual environment ---
VENV_DIR="$PROJECT_DIR/venv"
VENV_PYTHON_EXEC="$VENV_DIR/bin/python"
# --- END ADDED ---

echo "--- FermVault Update Script ---"
echo "Starting update in $PROJECT_DIR"

# --- 2. Check for Git Sanity (Optional, but good defense against user error) ---
if [ ! -d "$PROJECT_DIR/.git" ]; then
    echo "[ERROR] This directory does not appear to be a Git repository."
    echo "Please ensure you run 'git clone' first."
    exit 1
fi

# --- 3. *** NEW: Run Git Pull *** ---
echo "--- Pulling latest code from git... ---"
git pull
if [ $? -ne 0 ]; then
    echo "[ERROR] 'git pull' failed. Check for local changes or branch conflicts."
    exit 1
fi
echo "--- Git pull complete ---"
# --- END NEW ---

# --- 4. Run Dependency Installation (MODIFIED) ---
echo "Checking for new Python dependencies..."

# --- ADDED: Check if venv exists first ---
if [ ! -f "$VENV_PYTHON_EXEC" ]; then
    echo "[ERROR] Virtual environment not found at $VENV_PYTHON_EXEC"
    echo "This script only updates an existing installation."
    echo "Please run the ./install.sh script first."
    exit 1
fi
# --- END ADDED ---

# --- MODIFIED: Install packages using the venv's pip ---
# We call the python executable from the venv directly.
# The --user flag is removed.
"$VENV_PYTHON_EXEC" -m pip install -r "$PROJECT_DIR/requirements.txt"

# Check if pip installation succeeded
if [ $? -ne 0 ]; then
    echo "[FATAL ERROR] Dependency update failed. Check internet connection or requirements.txt."
    exit 1
fi


echo "--- Dependency Update Complete ---"
echo "If you ran this script manually, please restart the FermVault application."
