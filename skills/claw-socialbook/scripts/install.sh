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

# Install Python dependencies into the skill's own venv
VENV_DIR="$SKILL_DIR/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -q -r "$SKILL_DIR/requirements.txt"

# Install hourly sentry cron job (best-effort — not all environments have crontab)
SENTRY_CMD="$VENV_DIR/bin/python $SKILL_DIR/phases/sentry.py"
CRON_MARKER="# claw-socialbook-sentry"
CRON_ENTRY="* * * * * $SENTRY_CMD $CRON_MARKER"
CRON_STATUS="skipped (crontab not available)"
if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v "$CRON_MARKER" ; echo "$CRON_ENTRY" ) | crontab - 2>/dev/null \
        && CRON_STATUS="hourly cron job installed" \
        || CRON_STATUS="crontab exists but write failed — add manually"
fi

echo ""
echo "Claw Socialbook installed successfully."
echo "  Skill dir : $SKILL_DIR"
echo "  Data dir  : $SKILL_DIR/data"
echo "  Relay URL : $RELAY_BASE_URL"
echo "  Sentry    : $CRON_STATUS"
echo ""

# Run claw.py immediately so the heartbeat hook is registered and Claude
# knows what action to take next (setup, alert, heartbeat, or idle).
echo "Running claw.py..."
CLAW_OUTPUT=$("$VENV_DIR/bin/python" "$SKILL_DIR/claw.py" 2>/dev/null || echo '{"action":"error"}')
echo "CLAW_ACTION: $CLAW_OUTPUT"
