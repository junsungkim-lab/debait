import httpx
from .base import LLMResult

class AnthropicProvider:
    provider_name = "anthropic"

    async def generate(self, api_key: str, model: str, system: str, user: str, max_tokens: int) -> LLMResult:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        text = ""
        for c in data.get("content", []):
            if c.get("type") == "text":
                text += c.get("text", "")
        usage = data.get("usage", {}) or {}
        in_tok = int(usage.get("input_tokens", 0) or 0)
        out_tok = int(usage.get("output_tokens", 0) or 0)

        return LLMResult(text=text.strip(), input_tokens=in_tok, output_tokens=out_tok, provider="anthropic", model=model, cost_usd=0.0)
