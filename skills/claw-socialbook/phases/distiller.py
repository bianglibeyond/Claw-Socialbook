from __future__ import annotations

"""Phase 3: Distiller — context extraction, embedding, and fragment construction.

Reads user context via the ClawContextAdapter, asks Claude to distill it into
a MatchNature category + local_note, calls Gemini to embed the note, and
returns a fragment ready for bridge.py to publish.

BLOCKED: Lane B. OpenClawAdapter.extract_raw_context() raises NotImplementedError
until Open Q #1 is resolved (what data does openclaw.py read?).
Fallback: if adapter raises, prompt Claude to ask the user for context directly.
"""

import base64
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commons import vault, crypto
from commons.schema import MatchNature, Language, SocialAPP


EMBEDDING_MODEL = "gemini-embedding-2-preview"
EMBEDDING_DIM = 1536


def _embed(text: str, api_key: str) -> list[float]:
    """Embed text using Gemini. Returns 1536-dim vector."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
    )
    return list(result.embeddings[0].values)


def run(
    raw_context: str,
    match_nature: str,
    local_note: str,
    api_key: str,
    vault_path: Path = vault.VAULT_PATH,
) -> dict:
    """Build a fragment from distilled context.

    Args:
        raw_context: Full raw context string (from adapter or user prompt)
        match_nature: One of 'IDENTITY', 'PROBLEM', 'INTENT'
        local_note: Claude's short summary of what this fragment is about
        api_key: Gemini API key
        vault_path: Path to the vault DB

    Returns:
        dict with fragment fields ready for bridge.py
    """
    profile = vault.get_user_profile(vault_path)
    if not profile:
        return {"error": "vault not initialized"}

    # Generate ephemeral keypair for this fragment
    eph_priv, eph_pub = crypto.generate_keypair()
    eph_key_id = str(uuid.uuid4())
    fragment_id = str(uuid.uuid4())

    vault.store_keypair(
        key_id=eph_key_id,
        key_type="ephemeral",
        private_key=eph_priv,
        public_key=eph_pub,
        fragment_id=fragment_id,
        path=vault_path,
    )

    # Self-encrypt local_note as hint (relay privacy only)
    hint_encrypted_bytes = crypto.encrypt(local_note.encode(), eph_priv, eph_pub)
    hint_encrypted = base64.urlsafe_b64encode(hint_encrypted_bytes).rstrip(b"=").decode()

    # Embed the context
    vector = _embed(raw_context, api_key)

    # Get social apps from magic_links
    magic_links = vault.get_magic_links(vault_path)
    social_apps = list(magic_links.keys()) if magic_links else ["WHATSAPP"]

    languages = json.loads(profile.get("languages") or "[]") or ["ENGLISH"]
    regions = json.loads(profile.get("regions") or "[]") or []

    # Encode pubkey as base64url
    eph_pub_b64 = base64.urlsafe_b64encode(eph_pub).rstrip(b"=").decode()

    published_at = datetime.now(timezone.utc)
    expires_at = published_at + timedelta(hours=24)

    vault.store_fragment(
        {
            "fragment_id": fragment_id,
            "fragment_type": match_nature,
            "hint_encrypted": hint_encrypted,
            "local_note": local_note,
            "ephemeral_key_id": eph_key_id,
            "published_at": published_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "active",
        },
        vault_path,
    )

    return {
        "fragment_id": fragment_id,
        "ephemeral_key_id": eph_key_id,
        "ephemeral_pubkey": eph_pub_b64,
        "hint_encrypted": hint_encrypted,
        "local_note": local_note,
        "vector": vector,
        "fragment_type": match_nature,
        "social_apps": social_apps,
        "languages": languages,
        "regions": regions,
    }


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    result = run(
        raw_context=args["raw_context"],
        match_nature=args["match_nature"],
        local_note=args["local_note"],
        api_key=args["api_key"],
    )
    print(json.dumps(result))
