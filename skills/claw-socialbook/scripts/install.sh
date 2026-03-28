#!/usr/bin/env bash
set -euo pipefail
PREFIX=""
RELAY_BASE_URL=""
GEMINI_KEY=""
NO_CRON="0"
NO_CONFIGURE="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --relay-base-url) RELAY_BASE_URL="$2"; shift 2 ;;
    --gemini-key) GEMINI_KEY="$2"; shift 2 ;;
    --no-cron) NO_CRON="1"; shift 1 ;;
    --no-configure) NO_CONFIGURE="1"; shift 1 ;;
    *) shift 1 ;;
  esac
done
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_ID="claw-socialbook"
if [ -n "${OPENCLAW_HOME:-}" ]; then
  ROOT="$OPENCLAW_HOME"
elif [ -n "${CLAW_HOME:-}" ]; then
  ROOT="$CLAW_HOME"
else
  ROOT="$HOME/.openclaw"
fi
if [ -n "$PREFIX" ]; then
  ROOT="$PREFIX"
fi
SKILL_DIR="$ROOT/skills/$SKILL_ID"
DATA_DIR="$ROOT/data/$SKILL_ID"
mkdir -p "$SKILL_DIR" "$DATA_DIR/inbox" "$DATA_DIR/archive"
if command -v pip3 >/dev/null 2>&1; then
  pip3 install -r "$BASE_DIR/requirements.txt" || true
else
  if command -v pip >/dev/null 2>&1; then
    pip install -r "$BASE_DIR/requirements.txt" || true
  fi
fi
python3 - <<PY
import os, json, sys
base=os.path.abspath("$BASE_DIR")
cfg_path=os.path.join(base,"config.json")
cfg=json.load(open(cfg_path))
cfg["vault_db"]=os.path.join("$DATA_DIR","vault.db")
cfg["inbox_dir"]=os.path.join("$DATA_DIR","inbox")
cfg["archive_dir"]=os.path.join("$DATA_DIR","archive")
rb="$RELAY_BASE_URL"
if rb:
    cfg["relay_base_url"]=rb
gk="$GEMINI_KEY"
if gk:
    cfg["gemini_api_key"]=gk
json.dump(cfg, open(cfg_path,"w"), indent=2)
from core.vault import Vault
v=Vault(cfg["vault_db"])
_ = v.has_keypair() or v.generate()
PY
if [ "$NO_CRON" = "0" ]; then
  CRONLINE="0 * * * * cd \"$BASE_DIR\" && python3 \"$BASE_DIR/scripts/sentry.py\""
  EXISTING="$(crontab -l 2>/dev/null || true)"
  echo "$EXISTING" | grep -F "$BASE_DIR/scripts/sentry.py" >/dev/null 2>&1 || { printf "%s\n%s\n" "$EXISTING" "$CRONLINE" | crontab -; }
fi
if [ "$NO_CONFIGURE" = "0" ]; then
  python3 "$BASE_DIR/scripts/configure.py" ${RELAY_BASE_URL:+--relay-base-url "$RELAY_BASE_URL"} ${GEMINI_KEY:+--gemini-key "$GEMINI_KEY"} --non-interactive || true
fi
