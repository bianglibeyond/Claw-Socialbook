import os
import uuid
from typing import List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance
import redis

app = FastAPI(title="ClawSocialbook Blind Relay")

# --- Infrastructure Connections ---
# Railway automatically provides these environment variables if you link the services
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

q_client = QdrantClient(url=QDRANT_URL)
r_client = redis.from_url(REDIS_URL, decode_responses=True)

# Ensure Collection Exists (768 dimensions for Gemini)
COLLECTION_NAME = "socialbook_fragments"
try:
    q_client.get_collection(COLLECTION_NAME)
except:
    q_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=768, distance=Distance.COSINE),
    )

# --- Schemas ---
class Fragment(BaseModel):
    vector: List[float]
    pubkey: str # The agent's X25519 public key
    type: str   # SELF, STUCK, or INTENT

class Handshake(BaseModel):
    to_pubkey: str
    encrypted_payload: str

# --- Endpoints ---

@app.post("/publish")
async def publish(fragment: Fragment):
    point_id = str(uuid.uuid4())
    q_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id,
                vector=fragment.vector,
                payload={"pubkey": fragment.pubkey, "type": fragment.type}
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
    matches = [hit.payload["pubkey"] for hit in hits if hit.payload["pubkey"] != fragment.pubkey]
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