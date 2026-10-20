#!/usr/bin/env bash
# Render build script: runs once per deploy.
# Installs dependencies and collects static files into STATIC_ROOT so
# WhiteNoise can serve them from the WSGI app.
set -o errexit  # exit on error

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

python manage.py collectstatic --no-input
