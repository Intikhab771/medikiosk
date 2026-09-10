"""Provider-neutral LLM client contract."""

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str:
        """Return a model response for a supplied prompt."""
