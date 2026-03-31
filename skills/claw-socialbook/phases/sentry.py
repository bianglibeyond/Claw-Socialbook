from __future__ import annotations

"""Phase 2: Sentry — silent relay poller.

Runs every ~60 minutes (via claw.py heartbeat or OS scheduler). No LLM.
Polls the relay for new messages on each active fragment's mailbox.
Writes atomic signal files to inbox/ when new messages arrive.
Never floods: tracks last_seen_count per mailbox.

Output: number of new signal files written (for logging only).
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from commons import vault


def _poll_mailboxes(relay_base_url: str, ephemeral_pubkey: str) -> list[dict]:
    """Call /mailbox/poll-all for a given ephemeral pubkey."""
    try:
        resp = requests.post(
            f"{relay_base_url}/mailbox/poll-all",
            json={"ephemeral_pubkey": ephemeral_pubkey},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("mailboxes", [])
    except Exception:
        return []


def _write_signal_file(inbox_path: Path, mailbox_id: str, payload: dict) -> None:
    """Write signal file atomically: write to .tmp then os.rename."""
    inbox_path.mkdir(parents=True, exist_ok=True)
    tmp_path = inbox_path / f"{mailbox_id}.json.tmp"
    final_path = inbox_path / f"{mailbox_id}.json"
    tmp_path.write_text(json.dumps(payload, indent=2))
    os.rename(str(tmp_path), str(final_path))


def run(vault_path: Path = vault.VAULT_PATH, inbox_path: Path = vault.INBOX_PATH) -> int:
    """Poll relay for new messages and write signal files for any found.

    Returns count of new signal files written.
    """
    profile = vault.get_user_profile(vault_path)
    if not profile:
        return 0

    relay_base_url = profile.get("relay_base_url", "").rstrip("/")
    if not relay_base_url:
        return 0

    import base64

    # Collect unique pubkeys to poll:
    # 1. active fragments (for incoming new matches)
    # 2. any open mailbox's my_pubkey (fragment may have been expired locally
    #    but the mailbox is still live on the relay — e.g. a CONSENT in flight)
    seen_pubkeys: set[str] = set()
    fragment_id_for_pubkey: dict[str, str] = {}

    for fragment in vault.get_active_fragments(vault_path):
        fragment_id = fragment["fragment_id"]
        keypair = vault.get_keypair_for_fragment(fragment_id, vault_path)
        if not keypair:
            continue
        pubkey_b64 = base64.urlsafe_b64encode(keypair["public_key"]).rstrip(b"=").decode()
        seen_pubkeys.add(pubkey_b64)
        fragment_id_for_pubkey[pubkey_b64] = fragment_id

    for mb in vault.get_open_mailboxes(vault_path):
        pubkey_b64 = mb.get("my_pubkey", "")
        if pubkey_b64 and pubkey_b64 not in seen_pubkeys:
            seen_pubkeys.add(pubkey_b64)
            fragment_id_for_pubkey[pubkey_b64] = mb["my_fragment_id"]

    if not seen_pubkeys:
        return 0

    new_signals = 0

    for pubkey_b64 in seen_pubkeys:
        fragment_id = fragment_id_for_pubkey[pubkey_b64]

        mailboxes = _poll_mailboxes(relay_base_url, pubkey_b64)

        for mb in mailboxes:
            mailbox_id = mb.get("mailbox_id") or mb.get("mailbox", {}).get("mailbox_id")
            if not mailbox_id:
                continue

            messages = mb.get("messages", [])
            message_count = len(messages)

            # Determine my_role from the mailbox
            init_pubkey = mb.get("initiator_ephemeral_pubkey", "")
            my_role = "initiator" if init_pubkey == pubkey_b64 else "responder"
            peer_pubkey = (
                mb.get("responder_ephemeral_pubkey")
                if my_role == "initiator"
                else mb.get("initiator_ephemeral_pubkey")
            )

            # Upsert mailbox in vault (without overwriting last_seen_count)
            existing = vault.get_mailbox(mailbox_id, vault_path)
            last_seen = existing["last_seen_count"] if existing else 0

            vault.store_mailbox(
                {
                    "mailbox_id": mailbox_id,
                    "my_fragment_id": fragment_id,
                    "peer_fragment_id": (
                        mb.get("responder_fragment_id")
                        if my_role == "initiator"
                        else mb.get("initiator_fragment_id")
                    ),
                    "my_pubkey": pubkey_b64,
                    "peer_pubkey": peer_pubkey,
                    "my_role": my_role,
                    "mailbox_type": mb.get("mailbox_type", "REQUEST"),
                    "messages": messages,
                    "last_seen_count": last_seen,
                },
                vault_path,
            )

            if message_count > last_seen:
                # New messages — write signal file
                signal = {
                    "mailbox_id": mailbox_id,
                    "my_fragment_id": fragment_id,
                    "peer_fragment_id": (
                        mb.get("responder_fragment_id")
                        if my_role == "initiator"
                        else mb.get("initiator_fragment_id")
                    ),
                    "my_pubkey": pubkey_b64,
                    "peer_pubkey": peer_pubkey,
                    "my_role": my_role,
                    "messages": messages,
                    "mailbox_type": mb.get("mailbox_type", "REQUEST"),
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                }
                _write_signal_file(inbox_path, mailbox_id, signal)
                vault.update_mailbox_seen_count(mailbox_id, message_count, vault_path)
                new_signals += 1

    return new_signals


if __name__ == "__main__":
    count = run()
    print(json.dumps({"new_signals": count}))
