import httpx
from .base import LLMResult


class GoogleProvider:
    provider_name = "google"

    async def generate(self, api_key: str, model: str, system: str, user: str, max_tokens: int) -> LLMResult:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload, params={"key": api_key})
            r.raise_for_status()
            data = r.json()

        text = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                text += part.get("text", "")

        usage = data.get("usageMetadata", {})
        in_tok  = int(usage.get("promptTokenCount", 0) or 0)
        out_tok = int(usage.get("candidatesTokenCount", 0) or 0)

        return LLMResult(text=text.strip(), input_tokens=in_tok, output_tokens=out_tok, provider="google", model=model, cost_usd=0.0)
