import uuid
from datetime import datetime, timezone
from fastapi import FastAPI
from qdrant_client.models import PointStruct, VectorParams, Distance
from .database import get_qdrant_client, get_redis_client
from .schemas import FragmentPublishRequest, FragmentPublishResponse, Fragment

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
    resp = q_client.query_points(
        collection_name=COLLECTION_NAME,
        query=fragment_model.vector,
        # query_filter=Filter(
        #     must_not=[
        #         FieldCondition(
        #             key="ephemeral_pubkey",
        #             match=MatchValue(value=fragment_model.ephemeral_pubkey),
        #         )
        #     ]
        # ),
        limit=5,
    )
    hits = getattr(resp, "points", resp)
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
                "initiator_fragment_id": fragment_model.fragment_id,
                "response_fragment_id": rid,
                "initiator_ephemeral_pubkey": fragment_model.ephemeral_pubkey,
                "response_ephemeral_pubkey": (payload or {}).get("ephemeral_pubkey"),
                "score": score,
            }
        )
        if len(matches) >= 5:
            break
    return {
        "fragment_id": uuid.UUID(point_id),
        "hint": fragment_model.hint,
        "matches": matches,
    }

@app.post("/mailbox/send")
async def send_message(msg: Handshake):
    # Drop encrypted message into Redis list for that pubkey
    # TTL of 24 hours (86400 seconds)
    r_client.lpush(f"mail:{msg.to_pubkey}", msg.encrypted_payload)
    r_client.expire(f"mail:{msg.to_pubkey}", 86400)
    return {"status": "sent"}

@app.get("/mailbox/poll")
async def poll_messages(pubkey: str):
    # Pop all messages for this agent
    messages = []
    while True:
        m = r_client.rpop(f"mail:{pubkey}")
        if not m: break
        messages.append(m)
    return {"messages": messages}

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
