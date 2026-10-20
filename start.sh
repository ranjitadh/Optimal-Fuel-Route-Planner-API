#!/usr/bin/env bash
# Render start command: runs on every boot.
#
# Render's free instances have an ephemeral filesystem, so the SQLite database
# is recreated from scratch on each deploy/restart. This script therefore:
#   1. applies migrations,
#   2. (re)loads the committed fuel-stop CSV into the database, then
#   3. launches Gunicorn bound to Render's $PORT.
set -o errexit  # exit on error

python manage.py migrate --no-input

# Load the geocoded fuel stops. `--clear` guarantees a clean, deterministic
# dataset on every boot, which is safe because the source CSV is the source of
# truth and the data is read-only at runtime.
python manage.py load_fuel_prices --clear

python -m gunicorn core.wsgi:application --bind "0.0.0.0:${PORT:-8000}"
