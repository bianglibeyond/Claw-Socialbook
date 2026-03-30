# TODOS

## [PRE-LAUNCH] Re-enable server distribution endpoints
**What:** Un-comment `/client.tgz`, `/client.sha256`, `/install.sh` in `app/main.py` (commented out in commit 2feb319). Verify the install flow works end-to-end.
**Why:** The entire client distribution depends on these. Users can't install via one-line curl until they're live.
**Pros:** Unblocks the first real user install.
**Cons:** None. These were working before.
**Context:** Endpoints were commented out temporarily (2026-03-29). They need to be re-enabled and smoke-tested before the client build is distributed.
**Depends on:** Client build being packaged into `skills/claw-socialbook/`.

---

## [POST-LAUNCH] Qdrant TTL enforcement
**What:** Add a background task or scheduled sweep on the server that deletes Qdrant vectors where `creation_time + ttl_hours < now`.
**Why:** Redis mailboxes expire after 24h via `ex=86400`. Fragment vectors in Qdrant do not expire — they live forever. Users who stopped using the app still appear in match results indefinitely.
**Pros:** Match quality stays high as the network grows. Stale users don't dilute results.
**Cons:** Adds a background task to the server (FastAPI startup event + asyncio loop, or an external cron). Small complexity add.
**Context:** Qdrant does not support TTL natively on individual vectors. Options: (a) FastAPI lifespan background task that runs a sweep hourly, (b) Railway cron job that calls a cleanup endpoint, (c) store `expires_at` in Qdrant payload and filter on it in every `/match` query.
**Depends on:** None. Can be added independently of client work.

---

## [POST-LAUNCH] Rate limiting on relay endpoints
**What:** Add IP-based rate limiting to `/publish` and `/mailbox/send`.
**Why:** No auth, no rate limit. A script can flood the match space with spam fragments, degrading match quality for all users.
**Pros:** Protects match quality as the network grows. Simple to add.
**Cons:** IP-based rate limiting is easy to bypass (VPN, rotating IPs). Not a security guarantee, just a deterrent.
**Context:** Pre-launch with tiny user count, spam is theoretical. Post-launch with real users, this becomes a real risk. Railway supports middleware. Simple token bucket via Redis (already a dependency) is the natural choice.
**Depends on:** None.

---

## [FUTURE] Shared protocol package
**What:** Extract `commons/schema.py` (the request/response schema shared between client and server) into a standalone PyPI package: `claw-socialbook-protocol`.
**Why:** Currently copied between `app/schemas.py` (server) and `skills/claw-socialbook/commons/schema.py` (client). If the server schema changes (new field, renamed enum), the client copy drifts silently and produces wrong API requests.
**Pros:** Single source of truth for protocol. Version-pinnable. Any future claw implementation can import it.
**Cons:** Adds packaging infrastructure (pyproject.toml, PyPI publish step). Overkill pre-launch with one developer.
**Context:** Add a top-of-file comment to both copies for now: `# Mirrors [other file] at protocol version 2026-03-21. Update both when protocol changes.` Revisit when the protocol has multiple consumers.
**Depends on:** Protocol version stabilizing post-launch.
