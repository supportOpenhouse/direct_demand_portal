# Runs ON the droplet via `bash -s` (acres_call.sh fills the four base64 placeholders).
# Nothing is written to the droplet's disk; the token never leaves this shell.
set -u
B=https://www.99acres.com/99api
d() { printf '%s' "$1" | base64 -d; }
CREDS=$(d '__CREDS__'); METHOD=$(d '__METHOD__'); P=$(d '__PATH__'); BODY=$(d '__BODY__')
echo "egress: $(curl -4 -s --max-time 8 https://icanhazip.com/)  (must be 129.212.244.52)"
TOKEN=$(printf '%s' "$CREDS" | curl -s --max-time 30 -X POST "$B/v21/accesstoken/qwerty?rtype=json" \
  -H "Content-Type: application/json" -H "Accept: application/json" -H "Accept-Encoding: application/json" \
  --data-binary @- | python3 -c 'import sys,json
try: d = json.load(sys.stdin)
except ValueError: d = {}
print(d.get("accessToken") or d.get("accesstoken") or "")')
unset CREDS
[ -n "$TOKEN" ] || { echo "LOGIN FAILED (wrong login, or egress is not the Reserved IP)"; exit 1; }
H=(-H "Content-Type: application/json" -H "Accept: application/json" -H "Accept-Encoding: application/json"
   -H "Authorization: Bearer $TOKEN")
echo "== $METHOD $P"
if [ -n "$BODY" ]; then
  printf '%s' "$BODY" | curl -s --max-time 60 -w "\n[HTTP %{http_code}]\n" -X "$METHOD" "$B/$P" "${H[@]}" --data-binary @-
else
  curl -s --max-time 60 -w "\n[HTTP %{http_code}]\n" -X "$METHOD" "$B/$P" "${H[@]}"
fi
unset TOKEN
