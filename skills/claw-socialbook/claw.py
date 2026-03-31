from __future__ import annotations

"""Claw Socialbook — entrypoint state machine.

Called by Claude on every session start (via SKILL.md). Decides which phase
to run based on vault state and inbox contents. Returns structured JSON for
Claude to act on.

Dispatch order (CRITICAL — do not reorder):
  1. expire_stale_fragments()  — always first, no LLM
  2. setup_complete == 0       — run setup phase, stop
  3. signal files in inbox/    — run alert phase (FIRST priority over heartbeat)
  4. heartbeat due             — run distiller + bridge
  5. else                      — exit silently
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Allow running from the skill root or as a module
sys.path.insert(0, str(Path(__file__).resolve().parent))

from commons import vault
from commons.schema import CURRENT_VERSION

_SKILL_ROOT = Path(__file__).resolve().parent


def _check_for_update(relay_base_url: str) -> bool:
    """Return True if relay has a newer version than this install. Non-fatal on error."""
    try:
        import urllib.request
        url = relay_base_url.rstrip("/") + "/version"
        with urllib.request.urlopen(url, timeout=5) as resp:
            relay_version = resp.read().decode().strip()
        return relay_version != CURRENT_VERSION
    except Exception:
        return False


def _relay_base_url() -> str:
    relay_file = _SKILL_ROOT / "data" / "claw-socialbook-relay.txt"
    try:
        return relay_file.read_text().strip()
    except Exception:
        return ""


def _heartbeat_due(profile: dict) -> bool:
    last = profile.get("last_heartbeat_at")
    raw = profile.get("heartbeat_interval_hours")
    interval_h = int(raw) if raw is not None else 24
    if interval_h == 0:
        return True  # dev mode: always fire
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        return datetime.now(timezone.utc) >= last_dt + timedelta(hours=interval_h)
    except Exception:
        return True


def _list_signal_files(inbox_path: Path = vault.INBOX_PATH) -> list[str]:
    if not inbox_path.exists():
        return []
    return [p.name for p in sorted(inbox_path.glob("*.json"))]


def main() -> dict:
    """Run the dispatch state machine. Returns action dict for Claude."""
    vault_path = vault.VAULT_PATH

    # Step 0: initialize vault tables (idempotent)
    vault.init_vault(vault_path)

    # Step 1: expire stale fragments — always first
    expired = vault.expire_stale_fragments(vault_path)

    # Step 2: check setup
    profile = vault.get_user_profile(vault_path)
    if profile is None or not profile.get("setup_complete"):
        return {
            "action": "setup",
            "expired_fragments": expired,
            "message": "First run detected. Claude should run the setup phase.",
        }

    # Step 2.5: check for updates (non-blocking — skipped if relay unreachable)
    relay_url = _relay_base_url()
    if relay_url and _check_for_update(relay_url):
        return {
            "action": "update",
            "relay_base_url": relay_url,
            "message": "A newer version of Claw Socialbook is available.",
        }

    # Step 3: check inbox for signal files (highest priority)
    signal_files = _list_signal_files()
    if signal_files:
        return {
            "action": "alert",
            "signal_files": signal_files,
            "expired_fragments": expired,
            "message": f"Found {len(signal_files)} signal file(s). Run alert phase.",
        }

    # Step 4: check heartbeat
    if _heartbeat_due(profile):
        return {
            "action": "heartbeat",
            "expired_fragments": expired,
            "message": "Heartbeat due. Run distiller then bridge.",
        }

    # Step 5: nothing to do
    return {
        "action": "idle",
        "expired_fragments": expired,
        "message": "No action needed.",
    }


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2))
