import json
import os
import time
from typing import Any, Dict, List
from ..core import RelayClient, Vault


def _load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = _load_config(base_dir)
    client = RelayClient(cfg.get("relay_base_url", ""), cfg.get("api_key", ""))
    inbox_dir = os.path.join(base_dir, cfg.get("inbox_dir", "data/inbox"))
    os.makedirs(inbox_dir, exist_ok=True)
    vault = Vault(os.path.join(base_dir, cfg.get("vault_db", "data/vault.db")))
    ephs = vault.list_ephemeral_pubkeys()
    for eph in ephs:
        try:
            resp = client.mailbox_poll_all(eph)
        except Exception:
            continue
        mailboxes = resp.get("mailboxes", [])
        for mb in mailboxes:
            ts = int(time.time() * 1000)
            name = f"signal_{ts}_{os.getpid()}.json"
            path = os.path.join(inbox_dir, name)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(mb, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
