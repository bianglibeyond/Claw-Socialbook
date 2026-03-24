from random import random
import uuid
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization

# 1. Generate a private key
private_key = x25519.X25519PrivateKey.generate()
private_key_b = x25519.X25519PrivateKey.generate()

# 2. Derive the public key from the private key
public_key = private_key.public_key()
public_key_b = private_key_b.public_key()

# 3. Export to raw bytes (32 bytes)
public_bytes = public_key.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw
)
public_bytes_b = public_key_b.public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw
)

# print(f"Public Key (hex): {public_bytes.hex()}")

sample = {
    "protocol_version": "2026-03-21",
    "hint": "i read book lol",
    "fragment_type": "IDENTITY",
    "match_threshold": 0.85,
    "ephemeral_pubkey": public_bytes.hex(),
    "social_apps": [
        "WHATSAPP"
    ],
    "languages": [
        "ENGLISH"
    ],
    "region": [
        "us", 'japan'
    ]
}
sample['vector'] = [random() for _ in range(1536)]

sample_mailbox_send = {
    "protocol_version": "2026-03-21",
    "mailbox_id": None,
    "initiator_fragment_id": str(uuid.uuid4()),
    "responder_fragment_id": str(uuid.uuid4()),
    "initiator_ephemeral_pubkey": public_bytes.hex(),
    "responder_ephemeral_pubkey": public_bytes_b.hex(),
    "responder_fragment_hint": "responder hint",
    "initiator_fragment_hint": "initiator hint",
    "mailbox_type": "REQUEST",
    "sender_role": "initiator",
    "ciphertext": "SGVsbG8sIHRoaXMgaXMgZW5jcnlwdGVkIG1lc3NhZ2U="
}
