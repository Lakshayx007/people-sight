#!/usr/bin/env bash
# One build for local and Render: install, rebuild the database from data/raw, build the frontend.
set -euo pipefail
cd "$(dirname "$0")"
pip install -r backend/requirements.txt
python pipeline/02_clean_enps.py
python pipeline/03_clean_recruitment.py
python pipeline/04_build_db.py
cd frontend
npm ci
npm run build
