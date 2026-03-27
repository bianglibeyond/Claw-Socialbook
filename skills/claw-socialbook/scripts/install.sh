#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$DIR/data/inbox" "$DIR/data/archive"
python3 - <<'PY'
import os, sys, json
base=os.path.abspath(os.path.join(os.path.dirname(__file__),'..'))
sys.path.insert(0, base)
from core.vault import Vault
cfg=json.load(open(os.path.join(base,'config.json')))
db_path=os.path.join(base,cfg.get('vault_db','data/vault.db'))
v=Vault(db_path)
_=v.has_keypair() or v.generate()
PY
if command -v pip >/dev/null 2>&1; then
  pip install -r "$DIR/requirements.txt"
fi
