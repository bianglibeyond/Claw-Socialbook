from __future__ import annotations

"""Phase 5: Alert — process signal files and respond to peer messages.

Called by claw.py when signal files exist in inbox/. Reads each signal file,
decrypts the messages, and outputs structured JSON for Claude (via SKILL.md)
to decide: ignore, auto-respond, or escalate to the human.

Claude orchestrates the decision. This module handles:
  - Signal file reading + deletion
  - Message decryption
  - Structured output for Claude's judgment
  - Sending replies via the relay
"""

import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from commons import vault, crypto


def _b64decode_key(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _decrypt_message(ciphertext_b64: str, my_priv: bytes, peer_pub: bytes) -> str:
    try:
        ct = base64.urlsafe_b64decode(ciphertext_b64 + "=" * (-len(ciphertext_b64) % 4))
        plaintext = crypto.decrypt(ct, my_priv, peer_pub)
        return plaintext.decode("utf-8")
    except Exception as e:
        return f"[decryption failed: {e}]"


def _send_reply(
    relay_base_url: str,
    mailbox_id: str,
    signal: dict,
    ciphertext_b64: str,
    new_mailbox_type: str,
) -> bool:
    try:
        payload = {
            "mailbox_id": mailbox_id,
            "initiator_fragment_id": (
                signal["my_fragment_id"]
                if signal["my_role"] == "initiator"
                else signal["peer_fragment_id"]
            ),
            "responder_fragment_id": (
                signal["peer_fragment_id"]
                if signal["my_role"] == "initiator"
                else signal["my_fragment_id"]
            ),
            "initiator_ephemeral_pubkey": (
                signal["my_pubkey"]
                if signal["my_role"] == "initiator"
                else signal["peer_pubkey"]
            ),
            "responder_ephemeral_pubkey": (
                signal["peer_pubkey"]
                if signal["my_role"] == "initiator"
                else signal["my_pubkey"]
            ),
            "initiator_fragment_hint": "",
            "responder_fragment_hint": "",
            "mailbox_type": new_mailbox_type,
            "sender_role": signal["my_role"],
            "ciphertext": ciphertext_b64,
        }
        resp = requests.post(
            f"{relay_base_url}/mailbox/send",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False


def load_signal_files(inbox_path: Path = vault.INBOX_PATH) -> list[dict]:
    """Read all signal files. Returns list of parsed signal dicts."""
    signals = []
    for p in sorted(inbox_path.glob("*.json")):
        try:
            signals.append(json.loads(p.read_text()))
        except Exception:
            pass
    return signals


def process_signal(
    signal: dict,
    vault_path: Path = vault.VAULT_PATH,
) -> dict:
    """Decrypt messages in a signal file. Returns enriched dict for Claude.

    Claude reads this output and decides what to do.
    """
    my_fragment_id = signal["my_fragment_id"]
    keypair = vault.get_keypair_for_fragment(my_fragment_id, vault_path)
    if not keypair:
        return {**signal, "decrypted_messages": [], "error": "keypair not found"}

    my_priv = keypair["private_key"]
    peer_pub = _b64decode_key(signal.get("peer_pubkey", ""))

    decrypted = []
    for msg in signal.get("messages", []):
        ct = msg.get("ciphertext", "")
        plaintext = _decrypt_message(ct, my_priv, peer_pub)
        decrypted.append({
            "sender": msg.get("sender"),
            "created_at": msg.get("created_at") or msg.get("creation_time"),
            "plaintext": plaintext,
        })

    return {**signal, "decrypted_messages": decrypted}


def delete_signal_file(mailbox_id: str, inbox_path: Path = vault.INBOX_PATH) -> None:
    p = inbox_path / f"{mailbox_id}.json"
    if p.exists():
        p.unlink()


def send_consent(
    signal: dict,
    magic_link: str,
    relay_base_url: str,
    vault_path: Path = vault.VAULT_PATH,
) -> bool:
    """Encrypt and send magic link to peer as a CONSENT message."""
    my_fragment_id = signal["my_fragment_id"]
    keypair = vault.get_keypair_for_fragment(my_fragment_id, vault_path)
    if not keypair:
        return False

    my_priv = keypair["private_key"]
    peer_pub = _b64decode_key(signal["peer_pubkey"])

    ciphertext = crypto.encrypt(magic_link.encode(), my_priv, peer_pub)
    ct_b64 = base64.urlsafe_b64encode(ciphertext).rstrip(b"=").decode()

    success = _send_reply(
        relay_base_url=relay_base_url,
        mailbox_id=signal["mailbox_id"],
        signal=signal,
        ciphertext_b64=ct_b64,
        new_mailbox_type="CONSENT",
    )
    if success:
        vault.update_mailbox_type(signal["mailbox_id"], "CONSENT", vault_path)
    return success


def send_discuss(
    signal: dict,
    message: str,
    relay_base_url: str,
    vault_path: Path = vault.VAULT_PATH,
) -> bool:
    """Encrypt and send a DISCUSS message to peer (claw-to-claw auto-chat)."""
    my_fragment_id = signal["my_fragment_id"]
    keypair = vault.get_keypair_for_fragment(my_fragment_id, vault_path)
    if not keypair:
        return False

    my_priv = keypair["private_key"]
    peer_pub = _b64decode_key(signal["peer_pubkey"])

    ciphertext = crypto.encrypt(message.encode(), my_priv, peer_pub)
    ct_b64 = base64.urlsafe_b64encode(ciphertext).rstrip(b"=").decode()

    success = _send_reply(
        relay_base_url=relay_base_url,
        mailbox_id=signal["mailbox_id"],
        signal=signal,
        ciphertext_b64=ct_b64,
        new_mailbox_type="DISCUSS",
    )
    if success:
        vault.update_mailbox_type(signal["mailbox_id"], "DISCUSS", vault_path)
    return success


if __name__ == "__main__":
    # Called by SKILL.md: reads all signal files, outputs JSON for Claude
    signals = load_signal_files()
    processed = [process_signal(s) for s in signals]
    print(json.dumps(processed, indent=2))
