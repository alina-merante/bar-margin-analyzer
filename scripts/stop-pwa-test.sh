#!/usr/bin/env bash
set -Eeuo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/pwa-test-common.sh"
init_runtime
failed=0
for name in serve frontend backend tailscaled; do
    stop_managed "$name" || failed=1
done
(( failed == 0 )) || exit 1
echo "Ambiente PWA arrestato. Database, upload e stato Tailscale sono conservati."
