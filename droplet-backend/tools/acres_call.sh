#!/usr/bin/env bash
# One 99acres API call, made FROM THE DROPLET (the only whitelisted IP), driven from this Mac.
#
#   droplet-backend/tools/acres_call.sh GET  'v21/propertytype/qwerty?rtype=json&Res_Com=R&Mode=S'
#   droplet-backend/tools/acres_call.sh POST 'v21/listing/qwerty?rtype=json' '{"Res_Com":"R",...}'
#
# - Login comes from backend/.env (ACRES_DASHBOARD_USERNAME / _PASSWORD) and travels only inside
#   the SSH session (base64 in the script on stdin) — never in argv, never on the droplet's disk.
# - The token is fetched and used on the droplet; it never comes back to this Mac.
# - Output is printed with anything JWT-shaped redacted (a token was once leaked by a sloppy
#   summary script — see STATUS.md).
# - WRITES ARE REFUSED unless ALLOW_WRITE=1: a complete listing post creates a PUBLIC listing and
#   uses the pack's quota; delete/boost change live state. See docs/99acres-api.md.
set -euo pipefail
METHOD=${1:?usage: acres_call.sh METHOD 'path/after/99api/?query' [json-body]}
API_PATH=${2:?path after /99api/, e.g. v21/listing/qwerty?rtype=json}
BODY=${3:-}
HOST=${ACRES_DROPLET:-root@129.212.244.52}
case "$API_PATH" in
  v*/listing/*|*deleteListings*|*boost*)
    [ "${ALLOW_WRITE:-}" = 1 ] || { echo "refused: '$API_PATH' can change live 99acres data — re-run with ALLOW_WRITE=1 deliberately" >&2; exit 2; } ;;
esac
TOOLS=$(cd "$(dirname "$0")" && pwd)
cd "$TOOLS/../../backend"
CREDS=$(uv run --quiet python "$TOOLS/acres_creds.py")
enc() { printf '%s' "$1" | base64 | tr -d '\n'; }
C=$(enc "$CREDS"); unset CREDS
sed -e "s|__CREDS__|$C|" -e "s|__METHOD__|$(enc "$METHOD")|" \
    -e "s|__PATH__|$(enc "$API_PATH")|" -e "s|__BODY__|$(enc "$BODY")|" "$TOOLS/acres_remote.sh" \
  | ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" 'bash -s' 2>&1 \
  | python3 -c 'import re, sys
for line in sys.stdin:
    print(re.sub(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "<redacted-jwt>", line), end="")'
