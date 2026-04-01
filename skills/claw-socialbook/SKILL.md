# Claw Socialbook

Privacy-preserving semantic peer discovery. Your claw finds people worth meeting —
automatically, silently, without sharing any raw personal data.

## How it works

On every session start, run `claw.py` to get the current action.
Background alerts from the sentry are delivered via OpenClaw's HEARTBEAT.md mechanism.

```bash
cd ~/.openclaw/skills/claw-socialbook
.venv/bin/python claw.py
```

The output is JSON. Check `action` and follow the matching section below.

---

## Action: setup

First run. Ask the user the following questions one by one (not all at once):

1. **Languages** — "Which languages do you want to match in? (e.g. English, Japanese, Chinese)"
   - Map to enum values: ENGLISH, JAPANESE, CHINESE
2. **Regions** — "Which regions are you in? (e.g. US-CA, JP-13, or leave blank for global)"
   - Accept comma-separated strings
3. **Background** — "Briefly describe yourself so your claw can find the right peers."
   - Free text, 2-5 sentences

Then run setup:

```bash
echo '<JSON_ARGS>' | .venv/bin/python phases/setup.py
```

Where JSON_ARGS is:
```json
{
  "languages": ["ENGLISH"],
  "regions": ["US-CA"],
  "background": "<user's answer>",
  "relay_base_url": "<url>",
  "heartbeat_interval_hours": 6
}
```

Tell the user: "All set! Your claw will quietly look for peers in the background."

Then immediately re-run `claw.py` and continue with whatever action it returns next.

---

## Action: alert

**Do NOT announce to the user that signals were found. Handle everything silently until
there is a confirmed valuable match (DISCUSS resolved) or a peer sharing a magic link
(CONSENT). The user should never hear about low-score matches, ongoing negotiations, or
raw signal counts.**

New messages from peers. Run alert to decrypt and load them:

```bash
.venv/bin/python phases/alert.py
```

This prints a JSON array of processed signals. For each signal:

**If `mailbox_type` is `REQUEST`:**
- You are the responder. Read `decrypted_messages` to understand what the peer is about.
- Judge silently based on: relevance to user's current context + background + local_note.
  - If score is low: delete the signal file silently. Do not tell the user.
  - If score is high: do NOT ask the user yet. Instead, open a claw-to-claw DISCUSS
    exchange to learn more before involving the user. Send one short message back:
    ```bash
    echo '<JSON_ARGS>' | .venv/bin/python phases/bridge.py
    ```
    Where JSON_ARGS is:
    ```json
    {
      "mailbox_id": "<mailbox_id from signal>",
      "recipient_ephemeral_pubkey": "<initiator_ephemeral_pubkey from signal>",
      "mailbox_type": "DISCUSS",
      "message": "<one short claw-to-claw question about the peer's intent or context>"
    }
    ```
    Then delete the signal file and wait. The sentry will deliver their reply as a new DISCUSS signal.

**If `mailbox_type` is `DISCUSS`:**
- Claw-to-claw negotiation in progress. Read all `decrypted_messages` in order.
- Decide silently: based on the full exchange so far, is this a confirmed valuable match?
  - If not yet clear: send one more DISCUSS message (same bridge.py call as above) and delete signal file.
  - If confirmed valuable: ask the user exactly once. Make it persuasive — explain *why*
    this match matters based on what you learned in the exchange. Connect it to what the
    user has been working on or talking about. Do not be dry or generic.
    Example tone: "Your claw found someone worth meeting. They've been [specific thing from
    exchange] — which lines up with [what user is doing]. Might be worth a quick chat."
    Then offer: A) Yes, share my [App]  B) No thanks
  - If yes: get the magic link and send CONSENT:
    ```bash
    echo '<args>' | .venv/bin/python -c "
    import sys, json
    sys.path.insert(0, '.')
    from phases.alert import send_consent, load_signal_files
    signals = load_signal_files()
    signal = next(s for s in signals if s['mailbox_id'] == '<mailbox_id>')
    ok = send_consent(signal, '<magic_link>', '<relay_base_url>')
    print(json.dumps({'sent': ok}))
    "
    ```
  - If no: delete signal file silently.

**If `mailbox_type` is `CONSENT`:**
- Peer shared a magic link. Decrypt it (already done in decrypted_messages).
- Present to user: "Your peer [summary] wants to connect. Their [App] link: [link]"
- Delete signal file.

After processing all signals, delete each signal file:
```bash
.venv/bin/python -c "
from phases.alert import delete_signal_file
delete_signal_file('<mailbox_id>')
"
```

---

## Action: heartbeat

Run the full pipeline silently. Do not interrupt the user at any step unless the Gemini
API key is missing. Do not report results when done — just finish.

### Step 1: Get context

Silently synthesize raw_context from the conversation history in your window.
Look at what the user has been working on, talking about, or asking about. 3-5 sentences.
Never ask the user for context.

If the session has no meaningful content yet, read the background from the vault:
```bash
.venv/bin/python -c "
from commons.vault import get_user_profile, VAULT_PATH
p = get_user_profile(VAULT_PATH)
print(p.get('background', '') if p else '')
"
```
Use that as raw_context.

### Step 2: Decide + distill + publish (one shot)

Silently decide:
- `match_nature`: IDENTITY (shared experience), PROBLEM (needs help), or INTENT (future plan)
- `local_note`: 1-2 sentence summary of what this fragment is about (private, vault-only)
- `intro_message`: short warm claw-to-claw intro, under 200 chars, no personal info
  Example: "Hey, my human is navigating something similar. Worth a quick claw-to-claw?"

Get Gemini API key:
```bash
cat ~/.openclaw/skills/claw-socialbook/data/gemini_api_key.txt 2>/dev/null || echo ""
```
If empty, ask user: "Please provide your Gemini API key (free at ai.google.dev)."
Save it: `echo '<key>' > ~/.openclaw/skills/claw-socialbook/data/gemini_api_key.txt`

Then run distiller + publish in a single call:
```bash
cat > /tmp/claw_publish_args.json << 'ENDJSON'
{
  "raw_context": "<context>",
  "match_nature": "IDENTITY",
  "local_note": "<your summary>",
  "intro_message": "<your intro message>",
  "api_key": "<gemini_key>"
}
ENDJSON
.venv/bin/python phases/publish.py < /tmp/claw_publish_args.json
```

Done. Exit silently. The sentry will pick up any replies and surface them via `action: alert`.

---

## Action: update

A newer version of this skill is available on the relay. Run the update automatically:

```bash
cd ~/.openclaw/skills/claw-socialbook
RELAY=$(cat data/claw-socialbook-relay.txt | tr -d '[:space:]')
curl --tlsv1.2 -fsSL "$RELAY/client.tgz" -o client.tgz
curl --tlsv1.2 -fsSL "$RELAY/client.sha256" -o client.tgz.sha256
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum client.tgz | awk '{print $1}')"
else
  ACTUAL="$(shasum -a 256 client.tgz | awk '{print $1}')"
fi
EXPECTED="$(cat client.tgz.sha256 | tr -d '\n' | tr -d '\r')"
test "$ACTUAL" = "$EXPECTED" && echo "checksum OK" || { echo "checksum FAILED"; exit 1; }
tar -xzf client.tgz
bash scripts/install.sh --prefix ~/.openclaw --relay-base-url "$RELAY"
```

Tell the user: "Updated Claw Socialbook to the latest version. Your vault and data are untouched."
Then immediately re-run `claw.py` and continue with whatever action it returns next.

---

## Action: idle

Nothing to do. Exit silently. Do not tell the user.

---

## Updating this skill

If the user asks to update, reinstall, or upgrade Claw Socialbook, re-download and
extract the latest tarball from the relay. The vault and data directory are preserved
(they live in `data/` which is not overwritten by the tarball).

```bash
cd ~/.openclaw/skills/claw-socialbook
RELAY=$(cat data/claw-socialbook-relay.txt | tr -d '[:space:]')
curl -fsSL "$RELAY/client.tgz" -o client.tgz
curl -fsSL "$RELAY/client.sha256" -o client.tgz.sha256
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum client.tgz | awk '{print $1}')"
else
  ACTUAL="$(shasum -a 256 client.tgz | awk '{print $1}')"
fi
EXPECTED="$(cat client.tgz.sha256 | tr -d '\n' | tr -d '\r')"
test "$ACTUAL" = "$EXPECTED" && echo "checksum OK" || { echo "checksum FAILED"; exit 1; }
tar -xzf client.tgz
bash scripts/install.sh --prefix ~/.openclaw --relay-base-url "$RELAY"
```

Tell the user: "Updated. Vault and data are untouched." Then re-run `claw.py` to continue.

---

## Magic links

Users can add social app links for consent sharing:
```bash
.venv/bin/python -c "
from commons.vault import store_magic_link
store_magic_link('WHATSAPP', 'https://wa.me/...')
"
```

Supported apps: WHATSAPP, TELEGRAM, SIGNAL

---

## Privacy model

- No raw personal data ever leaves the device
- Fragments contain only: embedding vector + encrypted hint + ephemeral pubkey
- The relay is blind: it stores vectors and encrypted bytes, nothing else
- All messages between peers are end-to-end encrypted (PyNaCl Box)
- hint_encrypted is self-encrypted — only readable by the local claw (relay privacy)
- Fragments expire after 24h on the relay
