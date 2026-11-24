#!/bin/bash
cd "$(dirname "$0")"
echo "=== Shorts Bot setup (Mac) ==="
if ! command -v python3 >/dev/null || ! python3 -c "import sys; sys.exit(sys.version_info < (3,10))"; then
  echo "Python 3.10+ is needed. Opening the download page - install it, then run this again."
  open https://www.python.org/downloads/
  read -p "Press Enter to close"; exit 1
fi
[ -d venv ] || python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
echo; echo "Setup complete! Opening .env - paste your keys and save."
open -e .env
read -p "Press Enter to close"
