import asyncio
import httpx
from .base import LLMResult

MAX_RETRIES = 4
BASE_BACKOFF = 5  # seconds

class OpenAIProvider:
    provider_name = "openai"

    async def generate(self, api_key: str, model: str, system: str, user: str, max_tokens: int) -> LLMResult:
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_output_tokens": max_tokens,
        }

        for attempt in range(MAX_RETRIES):
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(url, headers=headers, json=payload)

            if r.status_code == 429:
                retry_after = int(r.headers.get("retry-after", BASE_BACKOFF * (2 ** attempt)))
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(retry_after)
                    continue
            r.raise_for_status()
            break

        data = r.json()
        text = ""
        for item in data.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        text += c.get("text", "")
        usage = data.get("usage", {}) or {}
        in_tok = int(usage.get("input_tokens", 0) or 0)
        out_tok = int(usage.get("output_tokens", 0) or 0)

        return LLMResult(text=text.strip(), input_tokens=in_tok, output_tokens=out_tok, provider="openai", model=model, cost_usd=0.0)
