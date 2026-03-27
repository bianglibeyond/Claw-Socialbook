import json
import os
from typing import Any
from ..core import Vault
from ..core.crypto import parse_pubkey_text, derive_shared_key, decrypt_message


def _load_config(base_dir: str) -> dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def socialbook_decrypt(ciphertext: str, my_ephemeral_pubkey: str, peer_ephemeral_pubkey: str) -> str:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = _load_config(base_dir)
    vault = Vault(os.path.join(base_dir, cfg.get("vault_db", "data/vault.db")))
    my_pub_b = parse_pubkey_text(my_ephemeral_pubkey)
    sk = vault.get_private_key_for_ephemeral_pub(my_pub_b)
    if sk is None:
        raise RuntimeError("private key not found for provided ephemeral key")
    shared = derive_shared_key(sk, parse_pubkey_text(peer_ephemeral_pubkey))
    return decrypt_message(ciphertext, shared)
