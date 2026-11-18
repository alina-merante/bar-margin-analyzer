#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/../.."
source scripts/pwa-test-common.sh

declare -f recover_managed_tailscaled >/dev/null

grep -Fq 'recover_managed_tailscaled ||' scripts/start-pwa-test.sh

bash -n scripts/pwa-test-common.sh
bash -n scripts/start-pwa-test.sh

echo "Controlli statici recupero Tailscale superati."
