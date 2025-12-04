#!/usr/bin/env bash
# Source .env, apply migrations, then run the respondent bank import.
set -euo pipefail

if [ -f ".env" ]; then
  set -a
  . ./.env
  set +a
fi

python manage.py migrate
./scripts/post_migration_sync.sh
