#!/bin/sh
# Postgres-style hybrid entrypoint: start as root, fix state-dir ownership,
# then drop privileges to the unprivileged `app` user (uid 1000).
set -e

if [ "$(id -u)" = "0" ]; then
    # Heals volumes left by older root-based images (self-healing migration).
    # For huge data dirs this chown can be guarded by a marker file as an optimisation.
    chown -R app:app /app/data
    exec gosu app "$@"
else
    # A compose `user:` override is in effect — respect it, but fail fast if the
    # volume is not writable by that uid instead of failing later at runtime
    # (e.g. sqlite "attempt to write a readonly database").
    if [ ! -w /app/data ]; then
        echo "FATAL: /app/data is not writable by uid $(id -u)." >&2
        echo "Fix ownership on the host: chown -R $(id -u) <volume>/_data" >&2
        exit 1
    fi
    exec "$@"
fi
