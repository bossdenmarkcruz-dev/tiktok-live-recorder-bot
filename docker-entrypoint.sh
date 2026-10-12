#!/bin/sh
set -eu
recordings_dir="${RECORDINGS_DIR:-/data/recordings}"
mkdir -p "$recordings_dir"
# Persistent volumes are often mounted as root-owned directories; adjust only the target directory.
chown botuser:botuser "$recordings_dir" 2>/dev/null || true
exec gosu botuser "$@"
