import os
import json
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import redis

def get_qdrant_client():
    url = os.getenv("QDRANT_URL")
    host = os.getenv("QDRANT_HOST", "qdrant")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    api_key = os.getenv("QDRANT_API_KEY")
    if url:
        if api_key:
            return QdrantClient(url=url, api_key=api_key)
        return QdrantClient(url=url)
    if api_key:
        return QdrantClient(host=host, port=port, api_key=api_key)
    return QdrantClient(host=host, port=port)

def ensure_collections(client: QdrantClient):
    vectors = VectorParams(size=3072, distance=Distance.COSINE) # Gemini Embedding 2 is 3072-dimension
    for name in ["identity_fragments", "stuckness_fragments", "intent_fragments"]:
        try:
            client.get_collection(name)
        except Exception:
            client.create_collection(collection_name=name, vectors_config=vectors)

def get_redis_client():
    url = os.getenv("REDIS_URL")
    if url:
        return redis.from_url(url, decode_responses=True)
    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD")
    db = int(os.getenv("REDIS_DB", "0"))
    return redis.Redis(host=host, port=port, password=password, db=db, decode_responses=True)

def mailbox_key(owner_hash: str) -> str:
    return f"mailbox:{owner_hash}"

def push_mail(r: redis.Redis, owner_hash: str, message: dict, ttl_seconds: int | None = None) -> bool:
    key = mailbox_key(owner_hash)
    r.lpush(key, json.dumps(message))
    if ttl_seconds:
        r.expire(key, ttl_seconds)
    return True

def poll_mail(r: redis.Redis, owner_hash: str, wait_seconds: int = 30) -> str | None:
    key = mailbox_key(owner_hash)
    item = r.brpop(key, timeout=wait_seconds)
    if item:
        return item[1]
    return None
