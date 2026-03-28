import json
import os
import sys
from typing import Any, Dict
from getpass import getpass
from ..core import RelayClient, Vault
import google.generativeai as genai
import argparse


def load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(base_dir: str, cfg: Dict[str, Any]) -> None:
    p = os.path.join(base_dir, "config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def ensure_gemini(cfg: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    key = (args.gemini_key or os.environ.get("GEMINI_API_KEY") or cfg.get("gemini_api_key", "")).strip()
    if args.non_interactive and not key:
        return cfg
    while not key:
        key = getpass("Enter Gemini API key (input hidden): ").strip()
    genai.configure(api_key=key)
    try:
        _ = genai.embed_content(model="models/text-embedding-004", content="hello")
    except Exception as e:
        print(f"Gemini check failed: {e}")
        return ensure_gemini(cfg, args)
    cfg["gemini_api_key"] = key
    return cfg


def ensure_relay(cfg: Dict[str, Any], args: argparse.Namespace) -> Dict[str, Any]:
    base = (args.relay_base_url or os.environ.get("CLAW_RELAY_BASE_URL") or cfg.get("relay_base_url", "")).strip()
    if args.non_interactive and not base:
        return cfg
    while not base:
        base = input("Enter Relay base URL (e.g., https://your.relay.host): ").strip()
    api_key = (os.environ.get("CLAW_RELAY_API_KEY") or cfg.get("api_key", "")).strip()
    if not api_key and not args.non_interactive:
        api_key = getpass("Enter Relay API key (input hidden, leave empty if not required): ").strip()
    client = RelayClient(base, api_key)
    try:
        _ = client.health()
    except Exception as e:
        print(f"Relay health check failed: {e}")
        return ensure_relay(cfg, args)
    cfg["relay_base_url"] = base
    cfg["api_key"] = api_key
    return cfg


def ensure_magic_links(base_dir: str, cfg: Dict[str, Any], args: argparse.Namespace) -> None:
    v = Vault(os.path.join(base_dir, cfg.get("vault_db", "data/vault.db")))
    pairs = {
        "whatsapp": args.magic_link_whatsapp,
        "signal": args.magic_link_signal,
        "telegram": args.magic_link_telegram,
    }
    for svc, provided in pairs.items():
        if provided:
            v.set_kv(f"magic_link_{svc}", provided)
    if args.non_interactive:
        return
    for svc in ("whatsapp", "signal", "telegram"):
        k = f"magic_link_{svc}"
        cur = v.get_kv(k) or ""
        val = input(f"Magic link for {svc} [{cur}]: ").strip() or cur
        if val:
            v.set_kv(k, val)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--relay-base-url")
    ap.add_argument("--gemini-key")
    ap.add_argument("--magic-link-whatsapp")
    ap.add_argument("--magic-link-signal")
    ap.add_argument("--magic-link-telegram")
    ap.add_argument("--non-interactive", action="store_true")
    args = ap.parse_args()
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = load_config(base_dir)
    cfg = ensure_gemini(cfg, args)
    cfg = ensure_relay(cfg, args)
    save_config(base_dir, cfg)
    ensure_magic_links(base_dir, cfg, args)
    print("Configuration updated.")


if __name__ == "__main__":
    main()
