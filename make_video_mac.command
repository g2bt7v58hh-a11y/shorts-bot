#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
read -p "What should the Short be about? " TOPIC
python make_short.py "$TOPIC"
open output
read -p "Press Enter to close"
