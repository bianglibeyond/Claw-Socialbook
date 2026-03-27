from typing import List
import google.generativeai as genai


class Embedder:
    def __init__(self, api_key: str, model: str = "models/text-embedding-004"):
        genai.configure(api_key=api_key)
        self.model = model

    def embed_text(self, text: str) -> List[float]:
        resp = genai.embed_content(model=self.model, content=text)
        values = resp.get("embedding")
        if values is None and hasattr(resp, "embedding"):
            values = resp.embedding
        return list(values or [])
