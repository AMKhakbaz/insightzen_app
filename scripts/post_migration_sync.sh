#!/usr/bin/env bash
# Run the respondent bank import after applying migrations, before starting application processes.
# Loads env vars (DB credentials, etc.) from .env if present before running.
set -euo pipefail

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

python manage.py import_respondent_bank --no-input
