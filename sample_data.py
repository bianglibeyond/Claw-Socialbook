from random import random
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization

# 1. Generate a private key
private_key = x25519.X25519PrivateKey.generate()

# 2. Derive the public key from the private key
public_key = private_key.public_key()

# 3. Export to raw bytes (32 bytes)
public_bytes = public_key.public_bytes(
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
