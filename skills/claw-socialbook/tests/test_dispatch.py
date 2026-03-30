from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from commons import vault
import claw


def test_dispatch_setup_when_no_profile(tmp_vault, monkeypatch):
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    monkeypatch.setattr(vault, "INBOX_PATH", inbox_path)
    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: [])

    result = claw.main()
    assert result["action"] == "setup"


def test_dispatch_setup_when_setup_incomplete(tmp_vault, monkeypatch):
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    vault.set_user_profile({"setup_complete": 0, "relay_base_url": "http://x"}, db_path)

    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: [])

    result = claw.main()
    assert result["action"] == "setup"


def test_dispatch_alert_when_signal_files_exist(tmp_vault, monkeypatch):
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    vault.set_user_profile({"setup_complete": 1, "relay_base_url": "http://x",
                            "heartbeat_interval_hours": 24,
                            "last_heartbeat_at": datetime.now(timezone.utc).isoformat()}, db_path)

    # Signal files exist
    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: ["mb-1.json"])

    result = claw.main()
    assert result["action"] == "alert"
    assert "mb-1.json" in result["signal_files"]


def test_dispatch_alert_before_heartbeat(tmp_vault, monkeypatch):
    """Alert takes priority over heartbeat even when heartbeat is due."""
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    # Heartbeat is due (old timestamp)
    vault.set_user_profile({
        "setup_complete": 1,
        "relay_base_url": "http://x",
        "heartbeat_interval_hours": 1,
        "last_heartbeat_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    }, db_path)

    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: ["mb-2.json"])

    result = claw.main()
    assert result["action"] == "alert"  # NOT heartbeat


def test_dispatch_heartbeat_when_due(tmp_vault, monkeypatch):
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    vault.set_user_profile({
        "setup_complete": 1,
        "relay_base_url": "http://x",
        "heartbeat_interval_hours": 1,
        "last_heartbeat_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
    }, db_path)
    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: [])

    result = claw.main()
    assert result["action"] == "heartbeat"


def test_dispatch_idle_when_heartbeat_not_due(tmp_vault, monkeypatch):
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    vault.set_user_profile({
        "setup_complete": 1,
        "relay_base_url": "http://x",
        "heartbeat_interval_hours": 24,
        "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }, db_path)
    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: [])

    result = claw.main()
    assert result["action"] == "idle"


def test_expire_stale_runs_before_dispatch(tmp_vault, monkeypatch):
    """expire_stale_fragments() must run even in idle state."""
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    vault.set_user_profile({
        "setup_complete": 1,
        "relay_base_url": "http://x",
        "heartbeat_interval_hours": 24,
        "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }, db_path)
    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: [])

    now = datetime.now(timezone.utc)
    vault.store_fragment({
        "fragment_id": "stale",
        "fragment_type": "IDENTITY",
        "hint_encrypted": "x",
        "local_note": "old",
        "ephemeral_key_id": "k1",
        "published_at": (now - timedelta(hours=48)).isoformat(),
        "expires_at": (now - timedelta(hours=24)).isoformat(),
        "status": "active",
    }, db_path)

    result = claw.main()
    # expired_fragments should be 1
    assert result["expired_fragments"] == 1
    assert vault.get_fragment("stale", db_path)["status"] == "expired"


def test_heartbeat_interval_zero_always_fires(tmp_vault, monkeypatch):
    """heartbeat_interval_hours=0 means dev mode: always fire."""
    db_path, inbox_path = tmp_vault
    monkeypatch.setattr(vault, "VAULT_PATH", db_path)
    vault.set_user_profile({
        "setup_complete": 1,
        "relay_base_url": "http://x",
        "heartbeat_interval_hours": 0,
        "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }, db_path)
    monkeypatch.setattr(claw, "_list_signal_files", lambda inbox_path=inbox_path: [])

    result = claw.main()
    assert result["action"] == "heartbeat"
