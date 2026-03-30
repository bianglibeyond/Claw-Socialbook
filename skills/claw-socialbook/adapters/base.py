from __future__ import annotations

from abc import ABC, abstractmethod


class ClawContextAdapter(ABC):
    """Interface for extracting raw user context from any claw implementation.

    Implement this for each claw variant (OpenClaw, ZeroClaw, NanoClaw, QClaw).
    The distiller calls extract_raw_context() to get the text it will embed.
    """

    @abstractmethod
    def extract_raw_context(self) -> str:
        """Return raw text representing the user's current context.

        Should capture the user's recent activity, background, or intent
        in plain text. The distiller will summarize and embed this.
        """
        ...
