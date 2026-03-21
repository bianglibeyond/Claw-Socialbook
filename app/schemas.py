import uuid
import base64
import binascii
from typing import List, Optional, Literal, Set
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import StrEnum
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

class MatchNature(StrEnum):
    IDENTITY = "IDENTITY" # to find a peer with similar experience
    PROBLEM = "PROBLEM" # to find an expert to solve a problem
    INTENT = "INTENT" # to find a peer to for a future event

class SocialAPP(StrEnum):
    WHATSAPP = "WHATSAPP"
    TELEGRAM = "TELEGRAM"
    SIGNAL = "SIGNAL"
    # more to be added

class Language(StrEnum):
    ENGLISH = "ENGLISH"
    JAPANESE = "JAPANESE"
    CHINESE = "CHINESE"
    # more to be added

class Protocol_Version(StrEnum):
    V_2026_03_21 = "2026-03-21"

class Fragment(BaseModel):
    # Meta
    protocol_version: Protocol_Version = Protocol_Version.V_2026_03_21
    fragment_id: uuid.UUID = Field(default_factory=uuid.uuid4)

    # Core Vector Data (1536 for Gemini Embedding 2 second best performanc)
    vector: List[float] = Field(..., min_items=1536, max_items=1536)

    # Match Logic
    fragment_type: MatchNature
    match_threshold: float = Field(default=0.85, ge=0.5, le=1.0)
    
    # Identity & Encryption
    ephemeral_pubkey: str # X25519 Public Key for the handshake

    # Discovery Constraints
    social_apps: Set[SocialAPP] = Field(..., min_items=1, max_items=len(SocialAPP))
    languages: Set[Language] = Field(..., min_items=1, max_items=len(Language))

    # Coarsened Location (Privacy-Preserving)
    region: Set[str] = Field(..., min_items=0, max_items=10)

    # Timeline
    creation_time: datetime
    ttl_hours: int = 24 # How long should the Relay keep this?

    @field_validator("ephemeral_pubkey")
    def validate_ephemeral_pubkey(cls, v: str):
        s = v.strip()
        try:
            b = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
        except Exception:
            try:
                b = base64.b64decode(s + "=" * (-len(s) % 4), validate=True)
            except Exception:
                if len(s) == 64:
                    try:
                        b = bytes.fromhex(s)
                    except (ValueError, binascii.Error):
                        raise ValueError("invalid hex")
                else:
                    raise ValueError("invalid base64/hex")
        if len(b) != 32:
            raise ValueError("must be 32 bytes")
        try:
            X25519PublicKey.from_public_bytes(b)
        except Exception:
            raise ValueError("not an X25519 public key")
        return v

class FragmentPublishRequest(BaseModel):
    fragment_type: MatchNature
    vector: List[float] = Field(..., min_items=1536, max_items=1536)
    ephemeral_pubkey: str # X25519 Public Key for the handshake
    social_apps: Set[SocialAPP] = Field(..., min_items=1, max_items=len(SocialAPP))
    country: str | None = None
    city: str | None = None
    languages: Set[Language] = Field(..., min_items=1, max_items=len(Language))

class FragmentPublishResponse(BaseModel):
    fragment_id: str
    # match_result: Optional[MatchItem] = None

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
