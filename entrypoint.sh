#!/bin/sh
# Railway mounts volumes as root:root. Fix ownership before starting the app.
STATE="${DATA_MOUNT_PATH:-/app/backend/data/state}"
mkdir -p "$STATE"
chown -R appuser:appuser "$STATE"
exec su-exec appuser "$@"
