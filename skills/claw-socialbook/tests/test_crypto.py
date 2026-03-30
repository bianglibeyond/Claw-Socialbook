from __future__ import annotations

import pytest
import nacl.exceptions

from commons.crypto import generate_keypair, encrypt, decrypt


def test_generate_keypair_returns_32_bytes_each():
    priv, pub = generate_keypair()
    assert len(priv) == 32
    assert len(pub) == 32


def test_generate_keypair_unique():
    priv1, pub1 = generate_keypair()
    priv2, pub2 = generate_keypair()
    assert priv1 != priv2
    assert pub1 != pub2


def test_encrypt_returns_nonempty_bytes():
    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    ct = encrypt(b"hello", a_priv, b_pub)
    assert isinstance(ct, bytes)
    assert len(ct) > 0


def test_same_message_different_ciphertext_each_call():
    """Nonce randomness: same inputs produce different ciphertext."""
    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    msg = b"consistent message"
    ct1 = encrypt(msg, a_priv, b_pub)
    ct2 = encrypt(msg, a_priv, b_pub)
    assert ct1 != ct2


def test_decrypt_roundtrip():
    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    msg = b"secret handshake"
    ct = encrypt(msg, a_priv, b_pub)
    result = decrypt(ct, b_priv, a_pub)
    assert result == msg


def test_decrypt_with_wrong_private_key_raises():
    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    wrong_priv, _ = generate_keypair()
    ct = encrypt(b"secret", a_priv, b_pub)
    with pytest.raises(nacl.exceptions.CryptoError):
        decrypt(ct, wrong_priv, a_pub)


def test_decrypt_with_tampered_ciphertext_raises():
    """CRITICAL: tamper detection must never silently return garbage."""
    a_priv, a_pub = generate_keypair()
    b_priv, b_pub = generate_keypair()
    ct = encrypt(b"authentic message", a_priv, b_pub)
    # Flip one bit in the middle of the ciphertext
    tampered = bytearray(ct)
    tampered[len(tampered) // 2] ^= 0x01
    with pytest.raises(nacl.exceptions.CryptoError):
        decrypt(bytes(tampered), b_priv, a_pub)


def test_self_encryption_roundtrip():
    """Self-encryption: used for hint_encrypted (relay privacy)."""
    priv, pub = generate_keypair()
    msg = b"my local note"
    ct = encrypt(msg, priv, pub)
    result = decrypt(ct, priv, pub)
    assert result == msg
