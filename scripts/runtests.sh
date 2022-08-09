#!/usr/bin/env bash
set -ex

# Ensure there are no errors.
python -W ignore manage.py check
#python -W ignore manage.py makemigrations --dry-run --check

# Check flake
#flake8 .

# Check imports
#isort . --check-only --rr

# Run tests
python manage.py test --verbosity=2 --noinput --keepdb --exclude-tag=ro_long_running --exclude-tag=performance --exclude-tag=need_repair --parallel="$(nproc)"
