from __future__ import annotations

import nacl.public
import nacl.exceptions


def generate_keypair() -> tuple[bytes, bytes]:
    """Generate a new X25519 keypair. Returns (private_key, public_key), each 32 bytes."""
    priv = nacl.public.PrivateKey.generate()
    return bytes(priv), bytes(priv.public_key)


def encrypt(message: bytes, sender_priv: bytes, recipient_pub: bytes) -> bytes:
    """Encrypt message using sender's private key and recipient's public key.

    Uses PyNaCl Box (Curve25519 DH + XSalsa20-Poly1305). Each call produces
    a different ciphertext due to random nonce prepended to the output.
    """
    box = nacl.public.Box(
        nacl.public.PrivateKey(sender_priv),
        nacl.public.PublicKey(recipient_pub),
    )
    return box.encrypt(message)


def decrypt(ciphertext: bytes, recipient_priv: bytes, sender_pub: bytes) -> bytes:
    """Decrypt ciphertext using recipient's private key and sender's public key.

    Raises nacl.exceptions.CryptoError on tamper or wrong keys. Never returns
    garbage — authentication failure always raises.
    """
    box = nacl.public.Box(
        nacl.public.PrivateKey(recipient_priv),
        nacl.public.PublicKey(sender_pub),
    )
    return box.decrypt(ciphertext)
