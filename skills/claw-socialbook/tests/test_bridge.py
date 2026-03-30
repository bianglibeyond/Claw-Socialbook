from __future__ import annotations

import base64
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import pytest

from commons import vault, crypto
from phases import bridge


def _make_fragment(db_path, fragment_type="IDENTITY"):
    """Helper: store a keypair + fragment and return the fragment dict."""
    priv, pub = crypto.generate_keypair()
    key_id = "eph-key-1"
    fragment_id = "frag-1"
    vault.store_keypair(key_id, "ephemeral", priv, pub, fragment_id, db_path)
    pub_b64 = base64.urlsafe_b64encode(pub).rstrip(b"=").decode()
    vault.store_fragment({
        "fragment_id": fragment_id,
        "fragment_type": fragment_type,
        "hint_encrypted": "enc",
        "local_note": "test",
        "ephemeral_key_id": key_id,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "status": "active",
    }, db_path)
    return {
        "fragment_id": fragment_id,
        "ephemeral_key_id": key_id,
        "ephemeral_pubkey": pub_b64,
        "hint_encrypted": "enc",
        "local_note": "test",
        "vector": [0.0] * 1536,
        "fragment_type": fragment_type,
        "social_apps": ["WHATSAPP"],
        "languages": ["ENGLISH"],
        "regions": [],
    }


def test_publish_creates_active_fragment(tmp_vault):
    db_path, _ = tmp_vault
    vault.set_user_profile({"relay_base_url": "http://relay", "setup_complete": 1}, db_path)
    fragment = _make_fragment(db_path)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"fragment_id": fragment["fragment_id"], "hint": "enc", "matches": []}
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp):
        result = bridge.run(fragment, "Hello peer!", db_path)

    assert result["published"] is True
    assert vault.get_fragment("frag-1", db_path)["status"] == "active"


def test_publish_expires_old_active_fragment_of_same_type(tmp_vault):
    db_path, _ = tmp_vault
    vault.set_user_profile({"relay_base_url": "http://relay", "setup_complete": 1}, db_path)

    # Store an existing active IDENTITY fragment
    vault.store_keypair("old-key", "ephemeral", b"\x01" * 32, b"\x02" * 32, "old-frag", db_path)
    vault.store_fragment({
        "fragment_id": "old-frag",
        "fragment_type": "IDENTITY",
        "hint_encrypted": "old-enc",
        "local_note": "old",
        "ephemeral_key_id": "old-key",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "status": "active",
    }, db_path)

    # New IDENTITY fragment
    fragment = _make_fragment(db_path, "IDENTITY")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"fragment_id": fragment["fragment_id"], "hint": "enc", "matches": []}
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp):
        bridge.run(fragment, "Hello!", db_path)

    assert vault.get_fragment("old-frag", db_path)["status"] == "expired"
    assert vault.get_fragment("frag-1", db_path)["status"] == "active"


def test_max_one_active_fragment_per_type(tmp_vault):
    """After publish, only 1 active IDENTITY fragment exists."""
    db_path, _ = tmp_vault
    vault.set_user_profile({"relay_base_url": "http://relay", "setup_complete": 1}, db_path)

    # Pre-existing old fragment
    vault.store_keypair("old-k", "ephemeral", b"\x01" * 32, b"\x02" * 32, "old-f", db_path)
    vault.store_fragment({
        "fragment_id": "old-f",
        "fragment_type": "IDENTITY",
        "hint_encrypted": "x",
        "local_note": "x",
        "ephemeral_key_id": "old-k",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "status": "active",
    }, db_path)

    fragment = _make_fragment(db_path, "IDENTITY")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"fragment_id": fragment["fragment_id"], "hint": "enc", "matches": []}
    mock_resp.raise_for_status.return_value = None

    with patch("requests.post", return_value=mock_resp):
        bridge.run(fragment, "Hi!", db_path)

    active = vault.get_active_fragments(db_path)
    identity_active = [f for f in active if f["fragment_type"] == "IDENTITY"]
    assert len(identity_active) == 1
    assert identity_active[0]["fragment_id"] == "frag-1"


def test_relay_failure_does_not_update_fragment_status(tmp_vault):
    """If relay call fails, fragment status must stay 'active' (not 'expired')."""
    db_path, _ = tmp_vault
    vault.set_user_profile({"relay_base_url": "http://relay", "setup_complete": 1}, db_path)
    fragment = _make_fragment(db_path)

    with patch("requests.post", side_effect=Exception("network error")):
        result = bridge.run(fragment, "Hi!", db_path)

    assert "error" in result
    # Fragment stays active — relay failure must not corrupt local state
    assert vault.get_fragment("frag-1", db_path)["status"] == "active"
