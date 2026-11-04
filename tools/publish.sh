#!/bin/bash
# Publishes this maps pack (id murder-mystery-maps); a server mounts it, a client never does. tools/ holds scripts the site refuses.
#   tools/publish.sh VERSION [extra publish_pack.sh flags, e.g. --site URL --token-file F --lock F --dry-run]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V=${1:?usage: tools/publish.sh VERSION [flags]}; shift
exec "$HERE/../dot-cloud/tools/publish_pack.sh" publish --source "$HERE" --id murder-mystery-maps --version "$V" --exclude-dir tools \
    --lock "$HERE/content.lock.json" "$@"
