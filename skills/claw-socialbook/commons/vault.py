from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_SKILL_ROOT = Path(__file__).resolve().parents[1]
VAULT_PATH = _SKILL_ROOT / "data" / "claw-socialbook.db"
INBOX_PATH = _SKILL_ROOT / "data" / "inbox"


def _conn(path: Path = VAULT_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_vault(path: Path = VAULT_PATH) -> None:
    """Create all tables. Idempotent — safe to call on every startup."""
    conn = _conn(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id INTEGER PRIMARY KEY,
            languages TEXT,
            regions TEXT,
            background TEXT,
            relay_base_url TEXT,
            setup_complete INTEGER DEFAULT 0,
            heartbeat_interval_hours INTEGER DEFAULT 24,
            last_heartbeat_at TEXT
        );
        CREATE TABLE IF NOT EXISTS keys (
            id TEXT PRIMARY KEY,
            key_type TEXT,
            fragment_id TEXT,
            private_key BLOB,
            public_key BLOB,
            created_at TEXT,
            used INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS fragments (
            fragment_id TEXT PRIMARY KEY,
            fragment_type TEXT,
            hint_encrypted TEXT,
            local_note TEXT,
            ephemeral_key_id TEXT,
            published_at TEXT,
            expires_at TEXT,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS mailboxes (
            mailbox_id TEXT PRIMARY KEY,
            my_fragment_id TEXT,
            peer_fragment_id TEXT,
            my_pubkey TEXT,
            peer_pubkey TEXT,
            my_role TEXT,
            mailbox_type TEXT,
            messages TEXT DEFAULT '[]',
            last_polled_at TEXT,
            created_at TEXT,
            last_seen_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS magic_links (
            app TEXT PRIMARY KEY,
            link TEXT
        );
    """)
    conn.close()
    INBOX_PATH.mkdir(parents=True, exist_ok=True)


# --- user_profile ---

def get_user_profile(path: Path = VAULT_PATH) -> Optional[dict[str, Any]]:
    conn = _conn(path)
    row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return None
    return dict(row)


def set_user_profile(data: dict[str, Any], path: Path = VAULT_PATH) -> None:
    conn = _conn(path)
    conn.execute("""
        INSERT INTO user_profile (id, languages, regions, background, relay_base_url,
            setup_complete, heartbeat_interval_hours, last_heartbeat_at)
        VALUES (1, :languages, :regions, :background, :relay_base_url,
            :setup_complete, :heartbeat_interval_hours, :last_heartbeat_at)
        ON CONFLICT(id) DO UPDATE SET
            languages = excluded.languages,
            regions = excluded.regions,
            background = excluded.background,
            relay_base_url = excluded.relay_base_url,
            setup_complete = excluded.setup_complete,
            heartbeat_interval_hours = excluded.heartbeat_interval_hours,
            last_heartbeat_at = excluded.last_heartbeat_at
    """, {
        "languages": json.dumps(data.get("languages", [])),
        "regions": json.dumps(data.get("regions", [])),
        "background": data.get("background", ""),
        "relay_base_url": data.get("relay_base_url", ""),
        "setup_complete": data.get("setup_complete", 0),
        "heartbeat_interval_hours": data.get("heartbeat_interval_hours", 24),
        "last_heartbeat_at": data.get("last_heartbeat_at"),
    })
    conn.close()


def mark_heartbeat(path: Path = VAULT_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(path)
    conn.execute(
        "UPDATE user_profile SET last_heartbeat_at = ? WHERE id = 1", (now,)
    )
    conn.close()


# --- keys ---

def store_keypair(
    key_id: str,
    key_type: str,
    private_key: bytes,
    public_key: bytes,
    fragment_id: Optional[str] = None,
    path: Path = VAULT_PATH,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(path)
    conn.execute(
        """INSERT INTO keys (id, key_type, fragment_id, private_key, public_key, created_at, used)
           VALUES (?, ?, ?, ?, ?, ?, 0)""",
        (key_id, key_type, fragment_id, private_key, public_key, now),
    )
    conn.close()


def get_keypair(key_id: str, path: Path = VAULT_PATH) -> Optional[dict[str, Any]]:
    conn = _conn(path)
    row = conn.execute("SELECT * FROM keys WHERE id = ?", (key_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_keypair_for_fragment(fragment_id: str, path: Path = VAULT_PATH) -> Optional[dict[str, Any]]:
    conn = _conn(path)
    row = conn.execute(
        "SELECT * FROM keys WHERE fragment_id = ? AND key_type = 'ephemeral'",
        (fragment_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# --- fragments ---

def store_fragment(data: dict[str, Any], path: Path = VAULT_PATH) -> None:
    conn = _conn(path)
    conn.execute(
        """INSERT INTO fragments
           (fragment_id, fragment_type, hint_encrypted, local_note,
            ephemeral_key_id, published_at, expires_at, status)
           VALUES (:fragment_id, :fragment_type, :hint_encrypted, :local_note,
            :ephemeral_key_id, :published_at, :expires_at, :status)""",
        data,
    )
    conn.close()


def get_fragment(fragment_id: str, path: Path = VAULT_PATH) -> Optional[dict[str, Any]]:
    conn = _conn(path)
    row = conn.execute(
        "SELECT * FROM fragments WHERE fragment_id = ?", (fragment_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_fragments(path: Path = VAULT_PATH) -> list[dict[str, Any]]:
    conn = _conn(path)
    rows = conn.execute(
        "SELECT * FROM fragments WHERE status = 'active'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_fragment_ids(path: Path = VAULT_PATH) -> set[str]:
    """Return all fragment IDs ever published from this vault (any status)."""
    conn = _conn(path)
    rows = conn.execute("SELECT fragment_id FROM fragments").fetchall()
    conn.close()
    return {r["fragment_id"] for r in rows}


def expire_stale_fragments(path: Path = VAULT_PATH) -> int:
    """Mark fragments where expires_at < now as 'expired'. Returns count updated."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(path)
    cur = conn.execute(
        "UPDATE fragments SET status = 'expired' WHERE status = 'active' AND expires_at < ?",
        (now,),
    )
    count = cur.rowcount
    conn.close()
    return count


def update_fragment_status(fragment_id: str, status: str, path: Path = VAULT_PATH) -> None:
    conn = _conn(path)
    conn.execute(
        "UPDATE fragments SET status = ? WHERE fragment_id = ?", (status, fragment_id)
    )
    conn.close()


# --- mailboxes ---

def store_mailbox(data: dict[str, Any], path: Path = VAULT_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(path)
    conn.execute(
        """INSERT INTO mailboxes
           (mailbox_id, my_fragment_id, peer_fragment_id, my_pubkey, peer_pubkey,
            my_role, mailbox_type, messages, last_polled_at, created_at, last_seen_count)
           VALUES (:mailbox_id, :my_fragment_id, :peer_fragment_id, :my_pubkey, :peer_pubkey,
            :my_role, :mailbox_type, :messages, :last_polled_at, :created_at, :last_seen_count)
           ON CONFLICT(mailbox_id) DO UPDATE SET
            mailbox_type = excluded.mailbox_type,
            messages = excluded.messages,
            last_polled_at = excluded.last_polled_at,
            last_seen_count = excluded.last_seen_count""",
        {
            "mailbox_id": data["mailbox_id"],
            "my_fragment_id": data["my_fragment_id"],
            "peer_fragment_id": data["peer_fragment_id"],
            "my_pubkey": data["my_pubkey"],
            "peer_pubkey": data["peer_pubkey"],
            "my_role": data["my_role"],
            "mailbox_type": data["mailbox_type"],
            "messages": json.dumps(data.get("messages", [])),
            "last_polled_at": data.get("last_polled_at", now),
            "created_at": data.get("created_at", now),
            "last_seen_count": data.get("last_seen_count", 0),
        },
    )
    conn.close()


def get_mailbox(mailbox_id: str, path: Path = VAULT_PATH) -> Optional[dict[str, Any]]:
    conn = _conn(path)
    row = conn.execute(
        "SELECT * FROM mailboxes WHERE mailbox_id = ?", (mailbox_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    d = dict(row)
    d["messages"] = json.loads(d.get("messages") or "[]")
    return d


def update_mailbox_seen_count(mailbox_id: str, count: int, path: Path = VAULT_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _conn(path)
    conn.execute(
        "UPDATE mailboxes SET last_seen_count = ?, last_polled_at = ? WHERE mailbox_id = ?",
        (count, now, mailbox_id),
    )
    conn.close()


def update_mailbox_type(mailbox_id: str, mailbox_type: str, path: Path = VAULT_PATH) -> None:
    conn = _conn(path)
    conn.execute(
        "UPDATE mailboxes SET mailbox_type = ? WHERE mailbox_id = ?",
        (mailbox_type, mailbox_id),
    )
    conn.close()


# --- magic_links ---

def store_magic_link(app: str, link: str, path: Path = VAULT_PATH) -> None:
    conn = _conn(path)
    conn.execute(
        "INSERT INTO magic_links (app, link) VALUES (?, ?) ON CONFLICT(app) DO UPDATE SET link = excluded.link",
        (app, link),
    )
    conn.close()


def get_magic_link(app: str, path: Path = VAULT_PATH) -> Optional[str]:
    conn = _conn(path)
    row = conn.execute("SELECT link FROM magic_links WHERE app = ?", (app,)).fetchone()
    conn.close()
    return row["link"] if row else None


def get_magic_links(path: Path = VAULT_PATH) -> dict[str, str]:
    conn = _conn(path)
    rows = conn.execute("SELECT app, link FROM magic_links").fetchall()
    conn.close()
    return {r["app"]: r["link"] for r in rows}
