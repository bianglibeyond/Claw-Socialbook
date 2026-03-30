import os
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
    vectors = VectorParams(size=1536, distance=Distance.COSINE) # Gemini Embedding 2 supports 1536-dimension
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
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE), # gemini-embedding-2-preview supports 768, 1536, 3072-dimension
        )
    except Exception:
        pass