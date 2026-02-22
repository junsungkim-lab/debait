from dataclasses import dataclass
from typing import Protocol

@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    provider: str = ""
    model: str = ""
    cost_usd: float = 0.0

class Provider(Protocol):
    provider_name: str
    async def generate(self, api_key: str, model: str, system: str, user: str, max_tokens: int) -> LLMResult: ...
