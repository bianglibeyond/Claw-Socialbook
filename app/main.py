import uuid
import json
from datetime import datetime
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from pathlib import Path
import tarfile
import io
import os
import hashlib
from qdrant_client.models import PointStruct, Filter, FieldCondition, MatchValue
from .database import q_client, r_client, COLLECTION_NAME
from .schemas import (
    FragmentPublishRequest,
    FragmentPublishResponse,
    FragmentMatchRequest,
    FragmentMatchResponse,
    Fragment,
    MailboxSendRequest,
    MailboxSendResponse,
    MailboxPollOneRequest,
    MailboxPollAllRequest,
    MailboxPollOneResponse,
    MailboxPollAllResponse,
    Mailbox,
    MailboxMessage,
    MailboxType,
)



app = FastAPI(title="ClawSocialbook Blind Relay")

# --- Endpoints ---

@app.post("/publish", response_model=FragmentPublishResponse)
async def publish(fragment: FragmentPublishRequest):
    fragment_model = Fragment(
        protocol_version=fragment.protocol_version,
        # fragment_id=uuid.uuid4(),
        vector=fragment.vector,
        hint=fragment.hint,
        fragment_type=fragment.fragment_type,
        match_threshold=fragment.match_threshold,
        ephemeral_pubkey=fragment.ephemeral_pubkey,
        social_apps=fragment.social_apps,
        languages=fragment.languages,
        region=fragment.region,
        # creation_time=datetime.now(timezone.utc),
        ttl_hours=24,
        did_match_history=[],
        non_match_history=[],
    )
    point_id = str(fragment_model.fragment_id)
    q_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector=fragment_model.vector,
                payload={
                    "protocol_version": fragment_model.protocol_version.value,
                    "hint": fragment_model.hint,
                    "fragment_type": fragment_model.fragment_type.value,
                    "match_threshold": fragment_model.match_threshold,
                    "ephemeral_pubkey": fragment_model.ephemeral_pubkey,
                    "languages": [lang.value for lang in fragment_model.languages],
                    "social_apps": [app.value for app in fragment_model.social_apps],
                    "region": list(fragment_model.region),
                    "creation_time": fragment_model.creation_time.isoformat(),
                    "ttl_hours": fragment_model.ttl_hours,
                    "did_match_history": [],
                    "non_match_history": [],
                },
            )
        ],
    )
    match_req = FragmentMatchRequest(
        protocol_version=fragment_model.protocol_version,
        vector=fragment_model.vector,
        hint=fragment_model.hint,
        fragment_type=fragment_model.fragment_type,
        match_threshold=fragment_model.match_threshold,
        ephemeral_pubkey=fragment_model.ephemeral_pubkey,
        social_apps=fragment_model.social_apps,
        languages=fragment_model.languages,
        region=fragment_model.region,
        initiator_fragment_id=fragment_model.fragment_id,
        initiator_fragment_hint=fragment_model.hint,
        limit=5,
    )
    match_resp = await match(match_req)
    return {
        "fragment_id": uuid.UUID(point_id),
        "hint": fragment_model.hint,
        "matches": match_resp.get("matches", []),
    }



@app.post("/match", response_model=FragmentMatchResponse)
async def match(fragment: FragmentMatchRequest):
    query_filter = Filter(
        must=[
            # FieldCondition(
            #     key="fragment_type",
            #     match=MatchValue(value=fragment.fragment_type.value),
            # )
        ],
        must_not=[
            FieldCondition(
                key="ephemeral_pubkey",
                match=MatchValue(value=fragment.ephemeral_pubkey),
            )
        ],
    )
    hits = []
    try:
        hits = q_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=fragment.vector,
            limit=fragment.limit,
            query_filter=query_filter,
        )
    except Exception:
        try:
            resp = q_client.query_points(
                collection_name=COLLECTION_NAME,
                query=fragment.vector,
                limit=fragment.limit,
                query_filter=query_filter,
            )
            hits = getattr(resp, "points", resp)
        except Exception:
            hits = []
    matches = []
    for h in hits:
        hid = getattr(h, "id", None) if not isinstance(h, dict) else h.get("id")
        payload = getattr(h, "payload", None) if not isinstance(h, dict) else h.get("payload", {})
        score = getattr(h, "score", None) if not isinstance(h, dict) else h.get("score")
        if hid is None:
            continue
        try:
            rid = uuid.UUID(str(hid))
        except Exception:
            continue
        matches.append(
            {
                "initiator_fragment_id": fragment.initiator_fragment_id,
                "responder_fragment_id": rid,
                "initiator_ephemeral_pubkey": fragment.ephemeral_pubkey,
                "responder_ephemeral_pubkey": (payload or {}).get("ephemeral_pubkey"),
                "initiator_fragment_hint": fragment.initiator_fragment_hint,
                "responder_fragment_hint": (payload or {}).get("hint"),
                "score": score if score is not None else 0.0,
            }
        )
        if len(matches) >= fragment.limit:
            break
    return {"matches": matches}



@app.post("/mailbox/send", response_model=MailboxSendResponse)
async def send_message(req: MailboxSendRequest):
    mailbox_id = req.mailbox_id or uuid.uuid4()
    key = f"mailbox:{mailbox_id}"
    raw = r_client.get(key)
    mailbox: Mailbox | None = None
    if raw:
        try:
            mailbox = Mailbox(**json.loads(raw))
        except Exception:
            mailbox = None
    if mailbox is None:
        mailbox = Mailbox(
            mailbox_id=mailbox_id,
            initiator_fragment_id=req.initiator_fragment_id,
            responder_fragment_id=req.responder_fragment_id,
            initiator_ephemeral_pubkey=req.initiator_ephemeral_pubkey,
            responder_ephemeral_pubkey=req.responder_ephemeral_pubkey,
            initiator_fragment_hint=req.initiator_fragment_hint,
            responder_fragment_hint=req.responder_fragment_hint,
            mailbox_type=req.mailbox_type,
            messages=[
                MailboxMessage(sender=req.sender_role, ciphertext=req.ciphertext),
            ],
        )
    else:
        mailbox.mailbox_type = MailboxType.CLOSED if req.mailbox_type == MailboxType.REJECT else req.mailbox_type
        mailbox.messages.append(MailboxMessage(sender=req.sender_role, ciphertext=req.ciphertext))
        if len(mailbox.messages) > 20:
            mailbox.messages = mailbox.messages[-20:]
    r_client.set(key, mailbox.model_dump_json(), ex=86400)
    for idx in (
        f"mailbox_index:{mailbox.initiator_fragment_id}",
        f"mailbox_index:{mailbox.responder_fragment_id}",
        f"mailbox_index_ephemeral:{mailbox.initiator_ephemeral_pubkey}",
        f"mailbox_index_ephemeral:{mailbox.responder_ephemeral_pubkey}",
    ):
        r_client.sadd(idx, str(mailbox.mailbox_id))
        r_client.expire(idx, 86400)
    if mailbox.mailbox_type is not MailboxType.CLOSED:
        for oidx in (
            f"mailbox_index_open:{mailbox.initiator_fragment_id}",
            f"mailbox_index_open:{mailbox.responder_fragment_id}",
            f"mailbox_index_ephemeral_open:{mailbox.initiator_ephemeral_pubkey}",
            f"mailbox_index_ephemeral_open:{mailbox.responder_ephemeral_pubkey}",
        ):
            r_client.sadd(oidx, str(mailbox.mailbox_id))
            r_client.expire(oidx, 86400)
    else:
        for oidx in (
            f"mailbox_index_open:{mailbox.initiator_fragment_id}",
            f"mailbox_index_open:{mailbox.responder_fragment_id}",
            f"mailbox_index_ephemeral_open:{mailbox.initiator_ephemeral_pubkey}",
            f"mailbox_index_ephemeral_open:{mailbox.responder_ephemeral_pubkey}",
        ):
            r_client.srem(oidx, str(mailbox.mailbox_id))
    return {"mailbox": mailbox}



#! Actually MailboxPollOneRequest restricts initiator and responder, but in this case it happens that it does not matter.
@app.post("/mailbox/poll-one", response_model=MailboxPollOneResponse)
async def poll_one_mailbox(req: MailboxPollOneRequest):
    a = r_client.smembers(f"mailbox_index_open:{req.initiator_fragment_id}")
    b = r_client.smembers(f"mailbox_index_open:{req.responder_fragment_id}")
    ids = a & b
    latest: Mailbox | None = None
    latest_ct: datetime | None = None
    for mid in ids:
        raw = r_client.get(f"mailbox:{mid}")
        if not raw:
            continue
        try:
            mb = Mailbox(**json.loads(raw))
        except Exception:
            continue
        ct = mb.creation_time
        if latest is None or (latest_ct is None) or (ct and ct > latest_ct):
            latest = mb
            latest_ct = ct
    return {"mailbox": latest}



@app.post("/mailbox/poll-all", response_model=MailboxPollAllResponse)
async def poll_all_mailbox(req: MailboxPollAllRequest):
    ids = r_client.smembers(f"mailbox_index_ephemeral_open:{req.ephemeral_pubkey}")
    items: list[Mailbox] = []
    for mid in ids:
        raw = r_client.get(f"mailbox:{mid}")
        if not raw:
            continue
        try:
            mb = Mailbox(**json.loads(raw))
        except Exception:
            continue
        items.append(mb)
    return {"mailboxes": items}



@app.get("/health")
async def health():
    q = "ok"
    r = "ok"
    try:
        q_client.get_collections()
    except Exception:
        q = "error"
    try:
        r_client.ping()
    except Exception:
        r = "error"
    return {"qdrant": q, "redis": r}


_client_tgz_cache: bytes | None = None

def _make_client_tgz() -> bytes:
    global _client_tgz_cache
    if _client_tgz_cache is not None:
        return _client_tgz_cache
    root = Path(__file__).resolve().parents[1] / "skills" / "claw-socialbook"
    buf = io.BytesIO()
    _EXCLUDE = {"__pycache__", ".pytest_cache", ".venv", "data", ".git"}
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in sorted(root.rglob("*")):  # sorted for determinism
            if p.is_file() and not any(part in _EXCLUDE for part in p.parts):
                rel = p.relative_to(root)
                tar.add(str(p), arcname=str(rel))
    buf.seek(0)
    _client_tgz_cache = buf.read()
    return _client_tgz_cache


@app.get("/client.tgz")
async def client_bundle(version: str | None = Query(default=None)):
    data = _make_client_tgz()
    return StreamingResponse(io.BytesIO(data), media_type="application/gzip")


@app.get("/client.sha256")
async def client_sha256(version: str | None = Query(default=None)):
    data = _make_client_tgz()
    h = hashlib.sha256()
    h.update(data)
    return PlainTextResponse(h.hexdigest() + "\n", media_type="text/plain")


@app.get("/install.sh")
async def install_sh(request: Request, version: str | None = Query(default=None)):
    base = f"https://{request.url.netloc}"
    script = f"""#!/usr/bin/env bash
set -euo pipefail
INSTALL_ROOT="${{OPENCLAW_HOME:-${{CLAW_HOME:-$HOME/.openclaw}}}}"
SKILL_ID="claw-socialbook"
INSTALL_DIR="$INSTALL_ROOT/skills/$SKILL_ID"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
URL_TGZ="{base}/client.tgz"
URL_SHA="{base}/client.sha256"
curl -fsSL "$URL_TGZ" -o client.tgz
curl -fsSL "$URL_SHA" -o client.tgz.sha256
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum client.tgz | awk '{{print $1}}')"
else
  ACTUAL="$(shasum -a 256 client.tgz | awk '{{print $1}}')"
fi
EXPECTED="$(cat client.tgz.sha256 | tr -d '\\n' | tr -d '\\r')"
test "$ACTUAL" = "$EXPECTED"
tar -xzf client.tgz
bash scripts/install.sh --prefix "$INSTALL_ROOT" --relay-base-url "{base}" "$@"
echo "ClawSocialbook client installed in $INSTALL_DIR"
"""
    return PlainTextResponse(script, media_type="text/x-shellscript")
