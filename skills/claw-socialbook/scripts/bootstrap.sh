#!/usr/bin/env bash
set -euo pipefail
PREFIX="${OPENCLAW_HOME:-${CLAW_HOME:-$HOME/.openclaw}}"
SERVER_URL="${SERVER_URL:-https://clawsocialbook-production.up.railway.app}"
while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --server-url) SERVER_URL="$2"; shift 2 ;;
    *) break ;;
  esac
done
mkdir -p "$PREFIX/skills"
cd "$PREFIX/skills"
curl -fsSL "$SERVER_URL/install.sh" | bash -s -- --prefix "$PREFIX" --relay-base-url "$SERVER_URL" "$@"
