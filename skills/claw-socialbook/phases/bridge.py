from __future__ import annotations

"""Phase 4: Bridge — publish fragment to relay and send outreach to matches.

Takes a distilled fragment (from distiller.py) and:
  1. Expires any existing active fragment of the same type (max 1 active per type)
  2. POSTs to /publish on the relay
  3. For each match returned, sends an encrypted REQUEST message

Fragment cap: at most 1 active fragment per MatchNature at any time.
If a previous active fragment exists for the same type, it is marked expired
locally AND its relay entry is naturally left to TTL (24h).
"""

import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from commons import vault, crypto


def _b64decode_key(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + padding)


def _expire_previous_active(
    fragment_type: str, new_fragment_id: str, vault_path: Path
) -> None:
    """Mark any existing active fragment of same type as expired (except the new one)."""
    active = vault.get_active_fragments(vault_path)
    for frag in active:
        if frag["fragment_type"] == fragment_type and frag["fragment_id"] != new_fragment_id:
            vault.update_fragment_status(frag["fragment_id"], "expired", vault_path)


def _send_request(
    relay_base_url: str,
    match: dict,
    my_fragment_id: str,
    my_pubkey: str,
    my_priv: bytes,
    intro_message: str,
) -> bool:
    """Send encrypted REQUEST message to a matched peer."""
    peer_pub_b64 = match.get("responder_ephemeral_pubkey", "")
    if not peer_pub_b64:
        return False

    try:
        peer_pub = _b64decode_key(peer_pub_b64)
        my_priv_bytes = my_priv
        ciphertext = crypto.encrypt(intro_message.encode(), my_priv_bytes, peer_pub)
        ct_b64 = base64.urlsafe_b64encode(ciphertext).rstrip(b"=").decode()

        payload = {
            "mailbox_id": None,
            "initiator_fragment_id": str(match["initiator_fragment_id"]),
            "responder_fragment_id": str(match["responder_fragment_id"]),
            "initiator_ephemeral_pubkey": my_pubkey,
            "responder_ephemeral_pubkey": peer_pub_b64,
            "initiator_fragment_hint": match.get("initiator_fragment_hint", ""),
            "responder_fragment_hint": match.get("responder_fragment_hint", ""),
            "mailbox_type": "REQUEST",
            "sender_role": "initiator",
            "ciphertext": ct_b64,
        }
        resp = requests.post(
            f"{relay_base_url}/mailbox/send",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()

        mb_data = resp.json().get("mailbox", {})
        mailbox_id = mb_data.get("mailbox_id")
        if mailbox_id:
            vault.store_mailbox(
                {
                    "mailbox_id": mailbox_id,
                    "my_fragment_id": my_fragment_id,
                    "peer_fragment_id": str(match["responder_fragment_id"]),
                    "my_pubkey": my_pubkey,
                    "peer_pubkey": peer_pub_b64,
                    "my_role": "initiator",
                    "mailbox_type": "REQUEST",
                    "messages": [],
                    "last_seen_count": 1,  # we just sent the first message
                },
            )
        return True
    except Exception:
        return False


def run(
    fragment: dict,
    intro_message: str,
    vault_path: Path = vault.VAULT_PATH,
) -> dict:
    """Publish fragment to relay and send REQUEST to all matches.

    Args:
        fragment: Output dict from distiller.run()
        intro_message: Encrypted intro message text (Claude writes this)
        vault_path: Path to the vault DB

    Returns:
        dict with publish result and outreach stats
    """
    profile = vault.get_user_profile(vault_path)
    if not profile:
        return {"error": "vault not initialized"}

    relay_base_url = profile.get("relay_base_url", "").rstrip("/")
    if not relay_base_url:
        return {"error": "relay_base_url not set"}

    fragment_id = fragment["fragment_id"]
    fragment_type = fragment["fragment_type"]

    # Expire previous active fragments of same type BEFORE publishing new one
    _expire_previous_active(fragment_type, fragment_id, vault_path)

    # Get ephemeral private key for this fragment
    keypair = vault.get_keypair(fragment["ephemeral_key_id"], vault_path)
    if not keypair:
        return {"error": "ephemeral keypair not found"}
    my_priv = keypair["private_key"]

    # Publish to relay
    publish_payload = {
        "protocol_version": "2026-03-21",
        "vector": fragment["vector"],
        "hint": fragment["hint_encrypted"],  # opaque bytes — relay stores as-is
        "fragment_type": fragment_type,
        "match_threshold": 0.85,
        "ephemeral_pubkey": fragment["ephemeral_pubkey"],
        "social_apps": fragment["social_apps"],
        "languages": fragment["languages"],
        "region": fragment["regions"],
    }

    try:
        resp = requests.post(
            f"{relay_base_url}/publish",
            json=publish_payload,
            timeout=30,
        )
        resp.raise_for_status()
        publish_resp = resp.json()
    except Exception as e:
        # Relay call failed — do not update fragment status
        return {"error": f"publish failed: {e}"}

    vault.mark_heartbeat(vault_path)

    matches = publish_resp.get("matches", [])
    outreach_sent = 0
    outreach_failed = 0

    for match in matches:
        ok = _send_request(
            relay_base_url=relay_base_url,
            match=match,
            my_fragment_id=fragment_id,
            my_pubkey=fragment["ephemeral_pubkey"],
            my_priv=my_priv,
            intro_message=intro_message,
        )
        if ok:
            outreach_sent += 1
        else:
            outreach_failed += 1

    return {
        "fragment_id": fragment_id,
        "published": True,
        "matches_found": len(matches),
        "outreach_sent": outreach_sent,
        "outreach_failed": outreach_failed,
    }


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    result = run(
        fragment=args["fragment"],
        intro_message=args["intro_message"],
    )
    print(json.dumps(result))
