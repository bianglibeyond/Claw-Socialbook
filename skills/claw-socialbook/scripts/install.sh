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

# Install per-minute claw cron job (best-effort — not all environments have crontab)
# Runs claw.py (which includes sentry inline). When signals are found, stamps an
# urgent marker into HEARTBEAT.md so OpenClaw picks them up at its next heartbeat.
CLAW_CRON_SCRIPT="$SKILL_DIR/scripts/claw_cron.sh"
cat > "$CLAW_CRON_SCRIPT" << 'CRONSCRIPT'
#!/usr/bin/env bash
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$SKILL_DIR/.venv/bin/python"
HEARTBEAT_MD="$HOME/.openclaw/workspace/HEARTBEAT.md"
URGENT_MARKER="claw-socialbook-urgent"

OUTPUT=$("$VENV" "$SKILL_DIR/claw.py" 2>/dev/null)
ACTION=$(echo "$OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('action',''))" 2>/dev/null)

if [ "$ACTION" = "alert" ]; then
    # Stamp urgent notice into HEARTBEAT.md so OpenClaw sees it immediately
    if [ -f "$HEARTBEAT_MD" ] && ! grep -q "$URGENT_MARKER" "$HEARTBEAT_MD"; then
        echo "" >> "$HEARTBEAT_MD"
        echo "<!-- $URGENT_MARKER -->" >> "$HEARTBEAT_MD"
        echo "- ⚡ URGENT [Claw Socialbook]: New peer signals arrived. Run \`cd $SKILL_DIR && .venv/bin/python claw.py\` NOW and follow SKILL.md." >> "$HEARTBEAT_MD"
    fi
elif [ "$ACTION" = "heartbeat" ] || [ "$ACTION" = "idle" ]; then
    # Remove urgent marker if no longer needed
    if [ -f "$HEARTBEAT_MD" ]; then
        grep -v "$URGENT_MARKER" "$HEARTBEAT_MD" | grep -v "URGENT \[Claw Socialbook\]" > "$HEARTBEAT_MD.tmp" && mv "$HEARTBEAT_MD.tmp" "$HEARTBEAT_MD"
    fi
fi
CRONSCRIPT
chmod +x "$CLAW_CRON_SCRIPT"

CRON_MARKER="# claw-socialbook-cron"
CRON_ENTRY="* * * * * $CLAW_CRON_SCRIPT $CRON_MARKER"
CRON_STATUS="skipped (crontab not available)"
if command -v crontab >/dev/null 2>&1; then
    ( crontab -l 2>/dev/null | grep -v "$CRON_MARKER" ; echo "$CRON_ENTRY" ) | crontab - 2>/dev/null \
        && CRON_STATUS="per-minute cron installed" \
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
