from datetime import timezone
import uuid
import base64
import binascii
from typing import List, Literal, Set
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



def validate_ephemeral_X25519_pubkey(v: str):
    s = v.strip()
    if len(s) == 64:
        try:
            b = bytes.fromhex(s)
            if len(b) == 32:
                X25519PublicKey.from_public_bytes(b)
                return v
        except (ValueError, binascii.Error):
            pass
    for decoder in (
        base64.urlsafe_b64decode,
        lambda x: base64.b64decode(x, validate=True),
    ):
        try:
            b = decoder(s + "=" * (-len(s) % 4))
            if len(b) == 32:
                X25519PublicKey.from_public_bytes(b)
                return v
        except Exception:
            continue
    raise ValueError("must be 32 bytes (base64) or 64 hex chars for X25519 public key")
    


class Match(BaseModel):
    initiator_fragment_id: uuid.UUID
    responder_fragment_id: uuid.UUID
    initiator_ephemeral_pubkey: str
    responder_ephemeral_pubkey: str
    initiator_fragment_hint: str
    responder_fragment_hint: str
    score: float = Field(..., ge=0.0, le=1.0)

    @field_validator("initiator_ephemeral_pubkey")
    def validate_initiator_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)
    
    @field_validator("responder_ephemeral_pubkey")
    def validate_responder_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)


class Fragment(BaseModel):
    # Meta
    protocol_version: Protocol_Version = Protocol_Version.V_2026_03_21
    fragment_id: uuid.UUID = Field(default_factory=uuid.uuid4)

    # Core Vector Data (1536 for Gemini Embedding 2 second best performanc)
    vector: List[float] = Field(..., min_items=1536, max_items=1536)
    hint: str # as user's information is not stored by the server, this hint helps the user's claw remember what information this fragment is about

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
    creation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_hours: int = 24 # How long should the Relay keep this?

    # Match History
    did_match_history: List[Match] = Field(default_factory=list)
    non_match_history: List[Match] = Field(default_factory=list)

    @field_validator("ephemeral_pubkey")
    def validate_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)



class FragmentPublishRequest(BaseModel):
    # Meta
    protocol_version: Protocol_Version = Protocol_Version.V_2026_03_21

    # Core Vector Data (1536 for Gemini Embedding 2 second best performance)
    vector: List[float] = Field(..., min_items=1536, max_items=1536)
    hint: str # as user's information is not stored by the server, this hint helps the user's claw remember what information this fragment is about

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

    @field_validator("ephemeral_pubkey")
    def validate_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)



class FragmentPublishResponse(BaseModel):
    fragment_id: uuid.UUID
    hint: str
    matches: List[Match] = Field(..., max_items=5)



class MailboxType(StrEnum):
    REQUEST = "REQUEST"
    DISCUSS = "DISCUSS"
    CONSENT = "CONSENT"
    REJECT = "REJECT"



class MailboxMessage(BaseModel):
    sender: Literal["initiator", "responder"]
    ciphertext: str
    creation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



class Mailbox(BaseModel):
    mailbox_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    initiator_fragment_id: uuid.UUID
    responder_fragment_id: uuid.UUID
    initiator_ephemeral_pubkey: str
    responder_ephemeral_pubkey: str
    initiator_fragment_hint: str
    responder_fragment_hint: str
    mailbox_type: MailboxType
    messages: List[MailboxMessage] = Field(..., min_items=1, max_items=20)
    creation_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("initiator_ephemeral_pubkey")
    def validate_initiator_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)
    
    @field_validator("responder_ephemeral_pubkey")
    def validate_responder_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)



class MailboxSendRequest(BaseModel):
    mailbox_id: uuid.UUID | None
    initiator_fragment_id: uuid.UUID
    responder_fragment_id: uuid.UUID
    initiator_ephemeral_pubkey: str
    responder_ephemeral_pubkey: str
    responder_fragment_hint: str
    initiator_fragment_hint: str
    mailbox_type: MailboxType
    sender_role: Literal["initiator", "responder"]
    ciphertext: str = Field(..., max_length=1024)

    @field_validator("initiator_ephemeral_pubkey")
    def validate_initiator_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)
    
    @field_validator("responder_ephemeral_pubkey")
    def validate_responder_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)



class MailboxSendResponse(BaseModel):
    mailbox: Mailbox



class MailboxPollRequest(BaseModel):
    fragment_id: uuid.UUID
    ephemeral_pubkey: str

    @field_validator("ephemeral_pubkey")
    def validate_ephemeral_pubkey(cls, v: str):
        return validate_ephemeral_X25519_pubkey(v)



class MailboxPollResponse(BaseModel):
    mailbox: Mailbox | None

