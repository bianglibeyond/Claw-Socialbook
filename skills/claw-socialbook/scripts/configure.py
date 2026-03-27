import json
import os
import sys
from typing import Any, Dict
from getpass import getpass
from ..core import RelayClient, Vault
import google.generativeai as genai


def load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(base_dir: str, cfg: Dict[str, Any]) -> None:
    p = os.path.join(base_dir, "config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def ensure_gemini(cfg: Dict[str, Any]) -> Dict[str, Any]:
    key = cfg.get("gemini_api_key", "").strip()
    while not key:
        key = getpass("Enter Gemini API key (input hidden): ").strip()
    genai.configure(api_key=key)
    try:
        _ = genai.embed_content(model="models/text-embedding-004", content="hello")
    except Exception as e:
        print(f"Gemini check failed: {e}")
        return ensure_gemini(cfg)
    cfg["gemini_api_key"] = key
    return cfg


def ensure_relay(cfg: Dict[str, Any]) -> Dict[str, Any]:
    base = cfg.get("relay_base_url", "").strip()
    while not base:
        base = input("Enter Relay base URL (e.g., https://your.relay.host): ").strip()
    api_key = cfg.get("api_key", "").strip()
    if not api_key:
        api_key = getpass("Enter Relay API key (input hidden, leave empty if not required): ").strip()
    client = RelayClient(base, api_key)
    try:
        _ = client.health()
    except Exception as e:
        print(f"Relay health check failed: {e}")
        return ensure_relay(cfg)
    cfg["relay_base_url"] = base
    cfg["api_key"] = api_key
    return cfg


def ensure_magic_links(base_dir: str, cfg: Dict[str, Any]) -> None:
    v = Vault(os.path.join(base_dir, cfg.get("vault_db", "data/vault.db")))
    for svc in ("whatsapp", "signal", "telegram"):
        k = f"magic_link_{svc}"
        cur = v.get_kv(k) or ""
        val = input(f"Magic link for {svc} [{cur}]: ").strip() or cur
        if val:
            v.set_kv(k, val)


def main() -> None:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = load_config(base_dir)
    cfg = ensure_gemini(cfg)
    cfg = ensure_relay(cfg)
    save_config(base_dir, cfg)
    ensure_magic_links(base_dir, cfg)
    print("Configuration updated.")


if __name__ == "__main__":
    main()
