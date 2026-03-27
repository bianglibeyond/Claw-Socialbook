import json
import os
from typing import Any, Dict, List
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization
from ..core import RelayClient, Embedder, Vault
from ..core.crypto import b64url_encode


def _load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def socialbook_publish_fragment(
    text: str,
    hint: str,
    fragment_type: str,
    social_apps: List[str],
    languages: List[str],
    region: List[str],
    match_threshold: float = 0.85,
) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = _load_config(base_dir)
    emb = Embedder(cfg.get("gemini_api_key", ""))
    vec = emb.embed_text(text)
    if len(vec) != 1536:
        if len(vec) > 1536:
            vec = vec[:1536]
        else:
            vec = vec + [0.0] * (1536 - len(vec))
    priv = x25519.X25519PrivateKey.generate()
    pub = priv.public_key()
    pub_b = pub.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)  # type: ignore
    eph_pub_b64 = b64url_encode(pub_b)
    payload = {
        "vector": vec,
        "hint": hint,
        "fragment_type": fragment_type,
        "match_threshold": match_threshold,
        "ephemeral_pubkey": eph_pub_b64,
        "social_apps": list({s.upper() for s in social_apps}),
        "languages": list({s.upper() for s in languages}),
        "region": list(region),
    }
    client = RelayClient(cfg.get("relay_base_url", ""), cfg.get("api_key", ""))
    resp = client.publish_fragment(payload)
    vault = Vault(os.path.join(base_dir, cfg.get("vault_db", "data/vault.db")))
    priv_b = priv.private_bytes(encoding=serialization.Encoding.Raw, format=serialization.PrivateFormat.Raw, encryption_algorithm=serialization.NoEncryption())  # type: ignore
    vault.store_fragment(str(resp.get("fragment_id")), hint, pub_b, priv_b)
    return resp
