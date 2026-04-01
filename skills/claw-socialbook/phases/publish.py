from __future__ import annotations

"""Phase 3+4 combined: Distill context and publish fragment in one subprocess.

Replaces the two-step distiller.py → bridge.py flow with a single call,
eliminating one Python startup and one AI reasoning cycle.

Input (stdin JSON):
    raw_context     : str   — synthesized context from conversation
    match_nature    : str   — IDENTITY | PROBLEM | INTENT
    local_note      : str   — 1-2 sentence private summary
    intro_message   : str   — claw-to-claw intro (<200 chars)
    api_key         : str   — Gemini API key

Output (stdout JSON):
    fragment_id, published, matches_found, outreach_sent, outreach_failed
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phases.distiller import run as distill
from phases.bridge import run as bridge


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())

    fragment = distill(
        raw_context=args["raw_context"],
        match_nature=args["match_nature"],
        local_note=args["local_note"],
        api_key=args["api_key"],
    )

    if "error" in fragment:
        print(json.dumps(fragment))
        sys.exit(1)

    result = bridge(
        fragment=fragment,
        intro_message=args["intro_message"],
    )

    print(json.dumps(result))
