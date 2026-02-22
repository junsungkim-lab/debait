import httpx
from .base import LLMResult


class GroqProvider:
    provider_name = "groq"

    async def generate(self, api_key: str, model: str, system: str, user: str, max_tokens: int) -> LLMResult:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage   = data.get("usage", {})
        in_tok  = int(usage.get("prompt_tokens", 0) or 0)
        out_tok = int(usage.get("completion_tokens", 0) or 0)

        return LLMResult(text=text.strip(), input_tokens=in_tok, output_tokens=out_tok, provider="groq", model=model, cost_usd=0.0)
