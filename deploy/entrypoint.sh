#!/bin/sh

# Fail immediately on an error or an unset variable so a partially prepared
# application can never begin serving traffic.
set -eu

# Validate the mutation flag before touching static files or the database. A
# typo must fail closed instead of silently skipping or unexpectedly running a
# staging seed operation.
case "${STAGING_SEED_DEMO:-0}" in
    0) seed_demo_enabled=0 ;;
    1) seed_demo_enabled=1 ;;
    *)
        echo "STAGING_SEED_DEMO must be exactly 0 or 1." >&2
        exit 64
        ;;
esac

# WhiteNoise serves immutable collected assets from this directory. Running
# collectstatic on every release also verifies the manifest before Gunicorn starts.
python manage.py collectstatic --noinput

# Apply schema changes before traffic reaches the new application process. This
# deployment intentionally permits one app replica only, avoiding migration races.
python manage.py migrate --noinput

# Demo data is an explicit staging-only opt-in. The command itself is idempotent,
# but no value other than the exact string "1" is allowed to trigger data writes.
if [ "${seed_demo_enabled}" = "1" ]; then
    python manage.py seed_demo
fi

# Replacing the shell preserves container signals so Gunicorn can stop cleanly.
exec "$@"
