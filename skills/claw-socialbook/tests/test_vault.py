from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from commons import vault


def test_init_vault_creates_tables(tmp_vault):
    db_path, _ = tmp_vault
    # Tables exist if we can query them without error
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert {"user_profile", "keys", "fragments", "mailboxes", "magic_links"} <= tables


def test_init_vault_idempotent(tmp_vault):
    db_path, _ = tmp_vault
    # Second call must not raise and must not lose data
    vault.set_user_profile({"background": "test", "relay_base_url": "http://x"}, db_path)
    vault.init_vault(db_path)
    profile = vault.get_user_profile(db_path)
    assert profile is not None
    assert profile["background"] == "test"


def test_get_user_profile_returns_none_when_empty(tmp_vault):
    db_path, _ = tmp_vault
    assert vault.get_user_profile(db_path) is None


def test_set_and_get_user_profile_roundtrip(tmp_vault):
    db_path, _ = tmp_vault
    data = {
        "languages": ["ENGLISH", "JAPANESE"],
        "regions": ["US-CA"],
        "background": "I build things",
        "relay_base_url": "https://relay.example.com",
        "setup_complete": 1,
        "heartbeat_interval_hours": 12,
        "last_heartbeat_at": None,
    }
    vault.set_user_profile(data, db_path)
    profile = vault.get_user_profile(db_path)
    assert profile is not None
    assert json.loads(profile["languages"]) == ["ENGLISH", "JAPANESE"]
    assert profile["background"] == "I build things"
    assert profile["setup_complete"] == 1
    assert profile["heartbeat_interval_hours"] == 12


def test_store_and_get_fragment_roundtrip(tmp_vault):
    db_path, _ = tmp_vault
    fid = "frag-001"
    data = {
        "fragment_id": fid,
        "fragment_type": "IDENTITY",
        "hint_encrypted": "enc-hint",
        "local_note": "building a social app",
        "ephemeral_key_id": "key-001",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "status": "active",
    }
    vault.store_fragment(data, db_path)
    frag = vault.get_fragment(fid, db_path)
    assert frag is not None
    assert frag["fragment_id"] == fid
    assert frag["fragment_type"] == "IDENTITY"
    assert frag["local_note"] == "building a social app"
    assert frag["status"] == "active"


def test_expire_stale_fragments_marks_only_expired(tmp_vault):
    db_path, _ = tmp_vault
    now = datetime.now(timezone.utc)

    # Already expired
    vault.store_fragment({
        "fragment_id": "old-frag",
        "fragment_type": "IDENTITY",
        "hint_encrypted": "x",
        "local_note": "old",
        "ephemeral_key_id": "k1",
        "published_at": (now - timedelta(hours=48)).isoformat(),
        "expires_at": (now - timedelta(hours=24)).isoformat(),
        "status": "active",
    }, db_path)

    # Not yet expired
    vault.store_fragment({
        "fragment_id": "fresh-frag",
        "fragment_type": "PROBLEM",
        "hint_encrypted": "y",
        "local_note": "fresh",
        "ephemeral_key_id": "k2",
        "published_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "status": "active",
    }, db_path)

    count = vault.expire_stale_fragments(db_path)
    assert count == 1

    old = vault.get_fragment("old-frag", db_path)
    fresh = vault.get_fragment("fresh-frag", db_path)
    assert old["status"] == "expired"
    assert fresh["status"] == "active"


def test_expire_stale_fragments_does_not_touch_non_expired(tmp_vault):
    db_path, _ = tmp_vault
    now = datetime.now(timezone.utc)
    vault.store_fragment({
        "fragment_id": "safe",
        "fragment_type": "INTENT",
        "hint_encrypted": "z",
        "local_note": "safe",
        "ephemeral_key_id": "k3",
        "published_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "status": "active",
    }, db_path)
    count = vault.expire_stale_fragments(db_path)
    assert count == 0
    assert vault.get_fragment("safe", db_path)["status"] == "active"


def test_magic_link_roundtrip(tmp_vault):
    db_path, _ = tmp_vault
    vault.store_magic_link("WHATSAPP", "https://wa.me/123", db_path)
    link = vault.get_magic_link("WHATSAPP", db_path)
    assert link == "https://wa.me/123"


def test_magic_link_upsert(tmp_vault):
    db_path, _ = tmp_vault
    vault.store_magic_link("TELEGRAM", "https://t.me/old", db_path)
    vault.store_magic_link("TELEGRAM", "https://t.me/new", db_path)
    assert vault.get_magic_link("TELEGRAM", db_path) == "https://t.me/new"


def test_get_magic_links_returns_all(tmp_vault):
    db_path, _ = tmp_vault
    vault.store_magic_link("WHATSAPP", "https://wa.me/1", db_path)
    vault.store_magic_link("SIGNAL", "https://signal.me/x", db_path)
    links = vault.get_magic_links(db_path)
    assert links["WHATSAPP"] == "https://wa.me/1"
    assert links["SIGNAL"] == "https://signal.me/x"


def test_mailbox_last_seen_count(tmp_vault):
    db_path, _ = tmp_vault
    vault.store_mailbox({
        "mailbox_id": "mb-1",
        "my_fragment_id": "f1",
        "peer_fragment_id": "f2",
        "my_pubkey": "mypub",
        "peer_pubkey": "peerpub",
        "my_role": "initiator",
        "mailbox_type": "REQUEST",
        "messages": [],
        "last_seen_count": 0,
    }, db_path)

    vault.update_mailbox_seen_count("mb-1", 3, db_path)
    mb = vault.get_mailbox("mb-1", db_path)
    assert mb["last_seen_count"] == 3
