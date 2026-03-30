from __future__ import annotations

from .base import ClawContextAdapter


class OpenClawAdapter(ClawContextAdapter):
    """Context adapter for OpenClaw.

    PENDING: Open Q #1 — what data does openclaw.py read?
    Options under consideration:
      a) Recent chat history from OpenClaw's session store
      b) Active project files / task context
      c) OpenClaw's own vault/memory table

    Until resolved, this raises NotImplementedError. The distiller falls back
    to prompting the user for context directly.
    """

    def extract_raw_context(self) -> str:
        raise NotImplementedError(
            "OpenClaw context extraction is pending resolution of Open Q #1. "
            "See adapters/openclaw.py for options. "
            "The distiller will prompt the user for context instead."
        )
