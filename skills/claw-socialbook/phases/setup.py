from __future__ import annotations

"""Phase 1: First-run setup.

Called by claw.py when setup_complete == 0. Prompts the user (via Claude's
conversation) for their profile, creates the vault, generates the master keypair,
and marks setup as complete.

This module is designed to be called from SKILL.md as a Claude-orchestrated phase.
The output is printed to stdout for Claude to present to the user.
"""

import json
import sys
import uuid
from pathlib import Path

# Allow running from the skill root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commons import vault, crypto


def run(
    languages: list[str],
    regions: list[str],
    background: str,
    relay_base_url: str,
    heartbeat_interval_hours: int = 6,
    vault_path: Path = vault.VAULT_PATH,
) -> dict:
    """Initialize the vault and user profile. Called once on first run.

    Args:
        languages: List of Language enum values (e.g. ["ENGLISH", "JAPANESE"])
        regions: List of region strings (e.g. ["US-CA", "JP-13"])
        background: Free-text user background description
        relay_base_url: Base URL of the relay server (e.g. "https://relay.example.com")
        heartbeat_interval_hours: How often to publish fragments (default 24h)

    Returns:
        dict with setup result info
    """
    vault.init_vault(vault_path)

    # Generate master keypair (used for identity, not per-fragment)
    master_priv, master_pub = crypto.generate_keypair()
    master_key_id = str(uuid.uuid4())
    vault.store_keypair(
        key_id=master_key_id,
        key_type="master",
        private_key=master_priv,
        public_key=master_pub,
        fragment_id=None,
        path=vault_path,
    )

    vault.set_user_profile(
        {
            "languages": languages,
            "regions": regions,
            "background": background,
            "relay_base_url": relay_base_url,
            "setup_complete": 1,
            "heartbeat_interval_hours": heartbeat_interval_hours,
            "last_heartbeat_at": None,
        },
        path=vault_path,
    )

    _register_alert_hook()

    return {
        "status": "ok",
        "master_key_id": master_key_id,
        "vault_path": str(vault_path),
        "message": "Setup complete. Claw Socialbook is ready.",
    }


def _register_alert_hook() -> None:
    """Append background alert check to ~/.openclaw/workspace/HEARTBEAT.md (idempotent)."""
    heartbeat_md = Path.home() / ".openclaw" / "workspace" / "HEARTBEAT.md"
    marker = "claw-socialbook-alert-hook"
    hook = (
        f"\n<!-- {marker} -->\n"
        "## Claw Socialbook\n"
        "Check for background peer alerts:\n"
        "`cat ~/.openclaw/skills/claw-socialbook/data/user_alert.json 2>/dev/null`\n"
        "If non-empty: surface it to the user, then delete the file:\n"
        "`rm ~/.openclaw/skills/claw-socialbook/data/user_alert.json`\n"
    )
    try:
        existing = heartbeat_md.read_text() if heartbeat_md.exists() else ""
        if marker not in existing:
            heartbeat_md.parent.mkdir(parents=True, exist_ok=True)
            with heartbeat_md.open("a") as f:
                f.write(hook)
    except Exception:
        pass  # non-fatal


if __name__ == "__main__":
    # Called by SKILL.md with JSON args on stdin
    args = json.loads(sys.stdin.read())
    result = run(
        languages=args["languages"],
        regions=args["regions"],
        background=args["background"],
        relay_base_url=args["relay_base_url"],
        heartbeat_interval_hours=args.get("heartbeat_interval_hours", 24),
    )
    print(json.dumps(result))
