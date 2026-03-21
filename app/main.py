import uuid
from typing import List, Literal, Field
from fastapi import FastAPI
from pydantic import BaseModel
from qdrant_client.models import PointStruct, VectorParams, Distance
from .database import get_qdrant_client, get_redis_client
from .schemas import FragmentPublishRequest, FragmentPublishResponse

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
            vectors_config=VectorParams(size=3072, distance=Distance.COSINE),
        )
    except Exception:
        pass

# --- Endpoints ---

@app.post("/publish")
async def publish(fragment: FragmentPublishRequest):
    point_id = str(uuid.uuid4())
    q_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector=fragment.vector,
                payload={
                    "pubkey": fragment.ephemeral_pubkey, 
                    "type": fragment.fragment_type,
                    "country": fragment.country,
                    "city": fragment.city,
                    "languages": [lang.value for lang in fragment.languages]
                }
            )
        ]
    )
    # Search for immediate matches (Top 3)
    hits = q_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=fragment.vector,
        limit=4 # 4 because it will find itself
    )
    # Filter out self and return potential peer pubkeys
    matches = [hit.payload["pubkey"] for hit in hits if hit.payload["pubkey"] != fragment.ephemeral_pubkey]
    return {"status": "published", "matches": matches}

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
