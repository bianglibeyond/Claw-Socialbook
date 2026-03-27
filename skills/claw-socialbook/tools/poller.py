import json
import os
import shutil
from typing import Any, Dict, List


def _load_config(base_dir: str) -> Dict[str, Any]:
    p = os.path.join(base_dir, "config.json")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def socialbook_poll() -> List[Dict[str, Any]]:
    base_dir = os.path.dirname(os.path.dirname(__file__))
    cfg = _load_config(base_dir)
    inbox_dir = os.path.join(base_dir, cfg.get("inbox_dir", "data/inbox"))
    archive_dir = os.path.join(base_dir, cfg.get("archive_dir", "data/archive"))
    os.makedirs(inbox_dir, exist_ok=True)
    os.makedirs(archive_dir, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(inbox_dir)):
        if not name.lower().endswith(".json"):
            continue
        src = os.path.join(inbox_dir, name)
        try:
            with open(src, "r", encoding="utf-8") as f:
                obj = json.load(f)
            items.append(obj)
            dst = os.path.join(archive_dir, name)
            shutil.move(src, dst)
        except Exception:
            pass
    return items
