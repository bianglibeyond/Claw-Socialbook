import uuid
import json
from datetime import datetime, timezone
from fastapi import FastAPI
from qdrant_client.models import PointStruct, VectorParams, Distance, Filter, FieldCondition, MatchValue
from .database import get_qdrant_client, get_redis_client
from .schemas import (
    FragmentPublishRequest,
    FragmentPublishResponse,
    FragmentMatchRequest,
    FragmentMatchResponse,
    Fragment,
    MailboxSendRequest,
    MailboxSendResponse,
    MailboxPollRequest,
    MailboxPollResponse,
    Mailbox,
    MailboxMessage,
)

app = FastAPI(title="ClawSocialbook Blind Relay")

# --- Infrastructure Connections ---

q_client = get_qdrant_client()
r_client = get_redis_client()

COLLECTION_NAME = "socialbook_fragments"
try:
    q_client.get_collection(COLLECTION_NAME)
except Exception:
    try:
        q_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
    except Exception:
        pass

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
        mailbox.messages.append(MailboxMessage(sender=req.sender_role, ciphertext=req.ciphertext))
        if len(mailbox.messages) > 20:
            mailbox.messages = mailbox.messages[-20:]
    r_client.set(key, mailbox.model_dump_json(), ex=86400)
    idx_a = f"mailbox_index:{mailbox.initiator_fragment_id}"
    idx_b = f"mailbox_index:{mailbox.responder_fragment_id}"
    r_client.sadd(idx_a, str(mailbox.mailbox_id))
    r_client.sadd(idx_b, str(mailbox.mailbox_id))
    r_client.expire(idx_a, 86400)
    r_client.expire(idx_b, 86400)
    return {"mailbox": mailbox}



@app.post("/mailbox/poll", response_model=MailboxPollResponse)
async def poll_messages(req: MailboxPollRequest):
    idx = f"mailbox_index:{req.fragment_id}"
    ids = r_client.smembers(idx) or []
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
