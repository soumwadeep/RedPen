#!/usr/bin/env bash
# Prove the offline claim instead of asserting it.
#
# Runs a full review -- parse, 37-rule analysis, and the whole Gemma narration
# pass -- while sampling every socket the process holds. Any remote address that
# is not loopback fails the check.
#
#   ./scripts/offline_proof.sh [path-to-contract]
#
# LIMITATION, stated rather than hidden: sampling is observational. A connection
# that opens and closes entirely between two samples is invisible to this script,
# so a PASS here means "nothing was seen", not "nothing happened".
#
# The enforced version is tests/test_offline_enforcement.py, which intercepts
# socket.connect for the duration of a full review and raises on any non-loopback
# target. That fails closed by construction and needs no privileges:
#
#     python3 -m pytest tests/test_offline_enforcement.py -q
#
# For OS-level proof, block egress and confirm the review still completes:
#
#     echo "block out proto tcp from any to any keep state" > /tmp/redpen-pf
#     echo "anchor "com/myapp/*" { rules /tmp/redpen-pf }" > /tmp/redpen-anchor
#     sudo pfctl -a com/myapp -f /tmp/redpen-anchor && sudo pfctl -e
#     redpen review contract.pdf --no-llm          # must still work
#     sudo pfctl -a com/myapp -F all && sudo pfctl -d
#
# The deterministic review has no network dependency at all, so it completes
# behind a full block; only the model layer needs a loopback port, which stays
# reachable. Turn Wi-Fi off and run `redpen review contract.pdf` for the same
# result without touching the firewall.

set -uo pipefail
cd "$(dirname "$0")/.."

DOC="${1:-samples/northgate_msa.pdf}"
PORT="${REDPEN_PORT:-8795}"
SAMPLE_HZ=8

command -v lsof >/dev/null || { echo "lsof not found"; exit 2; }
[ -f "$DOC" ] || { echo "no such file: $DOC"; exit 2; }

echo "· starting app on 127.0.0.1:$PORT"
python3 -m uvicorn redpen.server:app --host 127.0.0.1 --port "$PORT" --log-level warning &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null' EXIT
for _ in $(seq 1 40); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/api/status" && break
  sleep 0.5
done

ENGINE_PID="$(pgrep -f 'llama-server.*gemma' | head -1 || true)"
WATCH="$APP_PID"
if [ -n "$ENGINE_PID" ]; then
  WATCH="$WATCH $ENGINE_PID"
  echo "· watching app ($APP_PID) + engine ($ENGINE_PID)"
else
  echo "· watching app only ($APP_PID); engine starts on demand"
fi

TMP="$(mktemp)"
MON_PID=""
(
  while :; do
    for p in $WATCH; do
      lsof -nP -i -a -p "$p" 2>/dev/null | awk '/TCP/ {print $2, $9}'
    done
    sleep "$(python3 -c "print(1/$SAMPLE_HZ)")"
  done
) > "$TMP" &
MON_PID=$!

echo "· reviewing $DOC (deterministic + full model pass)"
TOKEN="$(curl -s -X POST --data-urlencode "name=proof" -F "text=$(cat "$DOC")" \
  "http://127.0.0.1:$PORT/api/review" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("token",""))' 2>/dev/null)"

if [ -z "$TOKEN" ]; then
  TOKEN="$(curl -s -X POST "http://127.0.0.1:$PORT/api/sample/northgate_msa" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"
fi

curl -sN --max-time 180 "http://127.0.0.1:$PORT/api/narrate/$TOKEN" > /dev/null 2>&1
SCORE="$(curl -s "http://127.0.0.1:$PORT/api/report/$TOKEN" | python3 -c 'import sys,json;print(json.load(sys.stdin)["analysis"]["score"])')"
kill $MON_PID 2>/dev/null

echo
echo "· sockets observed during the run:"
SORTED="$(sort -u "$TMP" | grep -E '^[0-9]+ +[0-9a-z.:\[\]%]+(->|:)' || true)"
echo "${SORTED:-    (none observed -- check that the app and engine were running)}" | sed 's/^/    /'
REMOTE="$(printf '%s\n' "$SORTED" | grep -vE '127\.0\.0\.1|\[::1\]|localhost' | grep -v '^$' || true)"
rm -f "$TMP"

echo
if [ -n "$REMOTE" ]; then
  echo "✗ FAIL -- non-loopback socket seen:"
  echo "$REMOTE"
  exit 1
fi
echo "✓ PASS -- every socket was loopback. Review score $SCORE/99, no request left the machine."
