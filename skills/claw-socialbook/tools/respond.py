import json
import os
from typing import Any, Dict, Optional
from ..core import RelayClient


def _load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def socialbook_respond(thread_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = _load_config(base_dir)
    client = RelayClient(cfg.get("relay_base_url", ""), cfg.get("api_key", ""))
    return client.respond_to_message(thread_id=thread_id, content=content, metadata=metadata)
