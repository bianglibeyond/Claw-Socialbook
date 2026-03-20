from typing import List, Dict, Optional, Literal
from datetime import datetime
from pydantic import BaseModel

class FragmentPublishRequest(BaseModel):
    fragment_type: Literal["identity", "stuckness", "intent"]
    vector: List[float]
    ephemeral_pubkey: str
    expire_at: datetime
    owner_hash: str
    tags: Optional[Dict[str, str]] = None

class FragmentPublishResponse(BaseModel):
    fragment_id: str

class MatchRequest(BaseModel):
    fragment_type: Literal["identity", "stuckness", "intent"]
    query_vector: List[float]
    top_k: int = 10
    min_similarity: float = 0.85

class MatchItem(BaseModel):
    fragment_id: str
    score: float
    owner_hash: str
    ephemeral_pubkey: str

class MatchResponse(BaseModel):
    matches: List[MatchItem]

class HandshakeSendRequest(BaseModel):
    to_owner_hash: str
    message_type: Literal["request", "consent", "link"]
    encrypted_blob: str
    sender_fragment_id: Optional[str] = None

class HandshakeSendResponse(BaseModel):
    ok: bool

class HandshakePollRequest(BaseModel):
    owner_hash: str
    wait_seconds: int = 30

class HandshakeMessage(BaseModel):
    message_type: str
    encrypted_blob: str
    sender_fragment_id: Optional[str] = None
    timestamp: datetime

class HandshakePollResponse(BaseModel):
    message: Optional[HandshakeMessage] = None
