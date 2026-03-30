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
