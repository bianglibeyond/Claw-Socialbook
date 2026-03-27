import json
import os
from typing import Any, Dict, Optional
from ..core import RelayClient, Vault
from ..core.crypto import parse_pubkey_text, derive_shared_key, encrypt_message
from cryptography.hazmat.primitives.asymmetric import x25519


def _load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def socialbook_mailbox_send(
    mailbox_id: Optional[str],
    initiator_fragment_id: str,
    responder_fragment_id: str,
    initiator_ephemeral_pubkey: str,
    responder_ephemeral_pubkey: str,
    initiator_fragment_hint: str,
    responder_fragment_hint: str,
    mailbox_type: str,
    sender_role: str,
    plaintext: str,
) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = _load_config(base_dir)
    vault = Vault(os.path.join(base_dir, cfg.get("vault_db", "data/vault.db")))
    if sender_role == "initiator":
        my_pub = initiator_ephemeral_pubkey
        peer_pub = responder_ephemeral_pubkey
    else:
        my_pub = responder_ephemeral_pubkey
        peer_pub = initiator_ephemeral_pubkey
    my_pub_b = parse_pubkey_text(my_pub)
    sk = vault.get_private_key_for_ephemeral_pub(my_pub_b)
    if sk is None:
        raise RuntimeError("private key not found for provided ephemeral key")
    shared = derive_shared_key(sk, parse_pubkey_text(peer_pub))
    ct = encrypt_message(plaintext, shared)
    payload = {
        "mailbox_id": mailbox_id,
        "initiator_fragment_id": initiator_fragment_id,
        "responder_fragment_id": responder_fragment_id,
        "initiator_ephemeral_pubkey": initiator_ephemeral_pubkey,
        "responder_ephemeral_pubkey": responder_ephemeral_pubkey,
        "responder_fragment_hint": responder_fragment_hint,
        "initiator_fragment_hint": initiator_fragment_hint,
        "mailbox_type": mailbox_type,
        "sender_role": sender_role,
        "ciphertext": ct,
    }
    client = RelayClient(cfg.get("relay_base_url", ""), cfg.get("api_key", ""))
    return client.mailbox_send(payload)
