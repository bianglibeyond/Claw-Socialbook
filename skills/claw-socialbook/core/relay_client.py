import os
from typing import Any, Dict, List, Optional
import json
import requests


class RelayClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        self.session.headers.update({"Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def publish_post(self, channel: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"channel": channel, "content": content, "metadata": metadata or {}}
        r = self.session.post(self._url("publish"), data=json.dumps(payload))
        r.raise_for_status()
        return r.json()

    def respond_to_message(self, thread_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = {"thread_id": thread_id, "content": content, "metadata": metadata or {}}
        r = self.session.post(self._url("respond"), data=json.dumps(payload))
        r.raise_for_status()
        return r.json()

    def poll_inbox(self) -> List[Dict[str, Any]]:
        r = self.session.get(self._url("inbox"))
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "items" in data:
            return data.get("items", [])
        if isinstance(data, list):
            return data
        return []
