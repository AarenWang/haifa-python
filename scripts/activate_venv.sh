#!/usr/bin/env bash

# Activate local virtual environment for this project and install requirements.
# Usage:
#   source scripts/activate_venv.sh

# Require sourcing to affect the current shell
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Please source this script: source scripts/activate_venv.sh" >&2
  exit 1
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR%/scripts}"

cd "$PROJECT_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtual environment at $VENV_DIR ..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  echo "Installing requirements from requirements.txt ..."
  pip install -r requirements.txt
else
  echo "requirements.txt not found; skipping dependency installation."
fi

echo "Environment activated. Python: $(python --version 2>/dev/null)"
echo "Virtualenv: $VIRTUAL_ENV"

