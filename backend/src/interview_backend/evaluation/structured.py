"""Server-owned structured generation using the existing paid-provider transports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StructuredPrompt:
    instructions: str
    data: dict
    schema: dict
    version: str = "star_grounded_v1"
    max_tokens: int = 2048
    max_request_bytes: int = 24000

    def __post_init__(self):
        if self.max_tokens != 2048 or self.max_request_bytes != 24000:
            raise ValueError("StructuredGenerationBudget")
