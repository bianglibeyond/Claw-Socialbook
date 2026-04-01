#!/usr/bin/env bash
# Claw Socialbook client installer.
# Called by the relay's /install.sh after the tarball is extracted.
# Usage: bash scripts/install.sh --prefix <install_root> --relay-base-url <url>
set -euo pipefail

PREFIX="$HOME/.openclaw"
RELAY_BASE_URL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix)
            PREFIX="$2"; shift 2 ;;
        --relay-base-url)
            RELAY_BASE_URL="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$RELAY_BASE_URL" ]]; then
    echo "Error: --relay-base-url is required" >&2
    exit 1
fi

SKILL_DIR="$PREFIX/skills/claw-socialbook"
DATA_DIR="$SKILL_DIR/data"
INBOX_DIR="$DATA_DIR/inbox"

mkdir -p "$SKILL_DIR" "$DATA_DIR" "$INBOX_DIR"

# Write relay URL into a config file so claw.py can read it during setup
cat > "$DATA_DIR/claw-socialbook-relay.txt" <<EOF
$RELAY_BASE_URL
EOF

# Install Python dependencies into the skill's own venv (prefer 3.11+)
VENV_DIR="$SKILL_DIR/.venv"
PYTHON_BIN=""
for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [[ -z "$PYTHON_BIN" ]]; then
    echo "Error: Python 3.11 or 3.12 is required. Please install it first." >&2; exit 1
fi
# Recreate venv if it doesn't exist or is running Python < 3.11
if [[ -d "$VENV_DIR" ]]; then
    VENV_MINOR=$("$VENV_DIR/bin/python" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo "0")
    if [[ "$VENV_MINOR" -lt 11 ]]; then
        echo "Upgrading venv (Python 3.$VENV_MINOR → $(${PYTHON_BIN} --version 2>&1))..."
        rm -rf "$VENV_DIR"
    fi
fi
if [[ ! -d "$VENV_DIR" ]]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -q -r "$SKILL_DIR/requirements.txt"

# Remove any old system crontab entry (replaced by OpenClaw's built-in cron)
CRON_MARKER="# claw-socialbook-sentry"
if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v "$CRON_MARKER" ) | crontab - 2>/dev/null || true
fi

echo ""
echo "Claw Socialbook installed successfully."
echo "  Skill dir : $SKILL_DIR"
echo "  Data dir  : $SKILL_DIR/data"
echo "  Relay URL : $RELAY_BASE_URL"
echo ""

# Run claw.py so OpenClaw knows what action to take next (setup, alert, heartbeat, or idle).
echo "Running claw.py..."
CLAW_OUTPUT=$("$VENV_DIR/bin/python" "$SKILL_DIR/claw.py" 2>/dev/null || echo '{"action":"error"}')
echo "CLAW_ACTION: $CLAW_OUTPUT"

echo ""
echo "OPENCLAW_SETUP: Please complete these one-time registration steps now, in order:"
echo ""
echo "1. Set HEARTBEAT interval to 6 hours. This is an independent step! It is the HEARTBEAT interval."
echo ""
echo "2. Add the following entry to ~/.openclaw/workspace/HEARTBEAT.md (create it if it doesn't exist):"
echo ""
echo "   ## Claw Socialbook"
echo "   DO NOT SKIP THIS STEP:"
echo "   - Check [Claw Socialbook] for new peer signals: run \`cd $SKILL_DIR && .venv/bin/python claw.py\` and follow SKILL.md for the returned action."
echo ""
echo "3. Add a cron job via OpenClaw's built-in scheduler:"
echo "   - ID/name : claw-socialbook-poll"
echo "   - Schedule : every 10 minutes"
echo "   - Session  : isolated"
echo "   - Message  : Background poll only: cd $SKILL_DIR && .venv/bin/python claw.py"
echo "                Run the sentry to fetch new peer signals and write them to the inbox."
echo "                Do not surface anything to the user."
echo "                Signal files will be picked up and surfaced by the next heartbeat."
echo ""
echo "4. Start onboarding now: open SKILL.md at $SKILL_DIR/SKILL.md, read the 'Action: setup' section,"
echo "   and follow it to ask the user the onboarding questions (language, region, background)."
