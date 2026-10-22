#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install production dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Apply database migrations
python manage.py migrate --noinput

# Guarded one-time admin recovery (executes only when explicitly enabled in environment)
if [ "$ADMIN_RECOVERY_ENABLED" = "true" ] || [ "$ADMIN_RECOVERY_ENABLED" = "1" ]; then
    echo "Admin recovery mode enabled. Executing guarded admin recovery command..."
    python manage.py ensure_admin_recovery
fi
