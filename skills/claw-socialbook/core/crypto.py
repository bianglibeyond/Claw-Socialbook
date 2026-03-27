import os
import base64
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization


def derive_shared_key(private_key: x25519.X25519PrivateKey, peer_public_key_bytes: bytes) -> bytes:
    peer_pub = x25519.X25519PublicKey.from_public_bytes(peer_public_key_bytes)
    shared = private_key.exchange(peer_pub)
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"socialbook:x25519")
    return kdf.derive(shared)


def encrypt_message(plaintext: str, key: bytes) -> str:
    aes = AESGCM(key)
    nonce = os.urandom(12)
    data = plaintext.encode("utf-8")
    ct = aes.encrypt(nonce, data, None)
    out = nonce + ct
    return base64.b64encode(out).decode("utf-8")


def decrypt_message(ciphertext_b64: str, key: bytes) -> str:
    raw = base64.b64decode(ciphertext_b64.encode("utf-8"))
    nonce = raw[:12]
    ct = raw[12:]
    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def load_private_key(raw: bytes) -> x25519.X25519PrivateKey:
    return x25519.X25519PrivateKey.from_private_bytes(raw)


def load_public_key(raw: bytes) -> x25519.X25519PublicKey:
    return x25519.X25519PublicKey.from_public_bytes(raw)


def b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("utf-8")


def b64url_decode(s: str) -> bytes:
    ss = s.strip()
    pad = "=" * (-len(ss) % 4)
    return base64.urlsafe_b64decode(ss + pad)


def parse_pubkey_text(s: str) -> bytes:
    st = s.strip()
    if len(st) == 64:
        try:
            b = bytes.fromhex(st)
            if len(b) == 32:
                return b
        except Exception:
            pass
    try:
        return b64url_decode(st)
    except Exception:
        return base64.b64decode(st)
