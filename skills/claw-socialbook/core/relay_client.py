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

    def publish_fragment(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.post(self._url("/publish"), data=json.dumps(payload))
        r.raise_for_status()
        return r.json()

    def mailbox_send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.session.post(self._url("/mailbox/send"), data=json.dumps(payload))
        r.raise_for_status()
        return r.json()

    def mailbox_poll_all(self, ephemeral_pubkey: str) -> Dict[str, Any]:
        r = self.session.post(self._url("/mailbox/poll-all"), data=json.dumps({"ephemeral_pubkey": ephemeral_pubkey}))
        r.raise_for_status()
        return r.json()

    def health(self) -> Dict[str, Any]:
        r = self.session.get(self._url("/health"))
        r.raise_for_status()
        return r.json()
