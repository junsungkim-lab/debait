from dataclasses import dataclass, field
from typing import Any, Dict, List
from . import prompts
from .router import rule_based_gate
from ..providers.openai_provider import OpenAIProvider
from ..providers.anthropic_provider import AnthropicProvider
from ..providers.google_provider import GoogleProvider
from ..providers.groq_provider import GroqProvider
from ..providers.mistral_provider import MistralProvider
from ..providers.base import LLMResult

PROVIDERS = {
    "openai":    OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google":    GoogleProvider(),
    "groq":      GroqProvider(),
    "mistral":   MistralProvider(),
}

DEFAULT_MAX_TOKENS = 800


@dataclass
class Budget:
    max_usd: float = 0.10
    max_tokens_per_stage: int = 800
    synth_max_tokens: int = 1200


def _split_model(full: str):
    if ":" in full:
        p, m = full.split(":", 1)
        return p, m
    return "openai", full


def _get_provider(model_str: str, fallback_provider=None, fallback_key: str = ""):
    provider_name, model_id = _split_model(model_str)
    provider = PROVIDERS.get(provider_name, fallback_provider)
    return provider, provider_name, model_id


def _build_stage_user_prompt(
    question: str,
    thread_summary: str,
    prev_results: List[Dict[str, str]],
) -> str:
    if not prev_results:
        parts = []
        if thread_summary:
            parts.append(f"Thread context:\n{thread_summary}\n")
        parts.append(f"Question: {question}")
        return "\n".join(parts)

    lines = [f"Question: {question}", ""]
    for r in prev_results:
        lines.append(f"{r['name']}:\n{r['text']}")
        lines.append("")
    return "\n".join(lines)


def _build_synth_user_prompt(question: str, stage_results: List[Dict[str, str]]) -> str:
    lines = [f"Q: {question}", ""]
    for r in stage_results:
        lines.append(f"{r['name']}:\n{r['text']}")
        lines.append("")
    lines.append("Final answer:")
    return "\n".join(lines)


async def run_orchestrator(
    *,
    question: str,
    thread_summary: str,
    user_api_keys: Dict[str, str],
    stages: List[Dict[str, str]],   # [{"name": str, "system_prompt": str, "model": str}]
    synth_model: str,
    budget: Budget,
    use_llm_gate: bool = False,
    gate_model: str = "openai:gpt-4o-mini",
) -> Dict[str, Any]:

    def _payload(result: LLMResult) -> Dict[str, Any]:
        return {
            "text": result.text,
            "provider": result.provider,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
        }

    if not stages:
        return {"final": "파이프라인 스테이지가 없습니다. Settings에서 스테이지를 추가해주세요."}

    # ── Gate 판단 ─────────────────────────────────────────────────────────────
    decision = rule_based_gate(question)
    if use_llm_gate:
        gp, gm = _split_model(gate_model)
        gkey = user_api_keys.get(gp)
        if gkey and gp in PROVIDERS:
            g = await PROVIDERS[gp].generate(
                api_key=gkey, model=gm,
                system=prompts.GATE_SYSTEM,
                user=prompts.gate_user(thread_summary, question),
                max_tokens=5,
            )
            if "MULTI" in g.text.upper():
                decision = "MULTI"
            elif "SIMPLE" in g.text.upper():
                decision = "SIMPLE"

    # ── 첫 번째 스테이지 (항상 실행) ──────────────────────────────────────────
    first = stages[0]
    fp, fn, fm = _get_provider(first["model"])
    fkey = user_api_keys.get(fn)
    if not fkey:
        return {"final": f"API Key가 없습니다: {fn}. Settings에서 등록해주세요."}

    first_result = await fp.generate(
        api_key=fkey,
        model=fm,
        system=first["system_prompt"],
        user=_build_stage_user_prompt(question, thread_summary, []),
        max_tokens=budget.max_tokens_per_stage,
    )

    # SIMPLE이거나 스테이지가 1개면 바로 반환
    if decision == "SIMPLE" or len(stages) == 1:
        return {
            "final": first_result.text,
            "decision": decision,
            "stages": [{"name": first["name"], "text": first_result.text}],
            "usage": {first["name"]: _payload(first_result)},
        }

    # ── 나머지 스테이지 순차 실행 ──────────────────────────────────────────────
    stage_results: List[Dict[str, str]] = [{"name": first["name"], "text": first_result.text}]
    usage: Dict[str, Any] = {first["name"]: _payload(first_result)}

    for stage in stages[1:]:
        sp, sn, sm = _get_provider(stage["model"])
        skey = user_api_keys.get(sn, fkey)  # 없으면 첫 번째 키로 폴백
        sprov = PROVIDERS.get(sn, fp)

        result = await sprov.generate(
            api_key=skey,
            model=sm,
            system=stage["system_prompt"],
            user=_build_stage_user_prompt(question, "", stage_results),
            max_tokens=budget.max_tokens_per_stage,
        )
        stage_results.append({"name": stage["name"], "text": result.text})
        usage[stage["name"]] = _payload(result)

    # ── Synth (항상 마지막) ────────────────────────────────────────────────────
    yp, yn, ym = _get_provider(synth_model)
    ykey = user_api_keys.get(yn, fkey)
    yprov = PROVIDERS.get(yn, fp)

    synth_result = await yprov.generate(
        api_key=ykey,
        model=ym,
        system=prompts.SYNTH_SYSTEM,
        user=_build_synth_user_prompt(question, stage_results),
        max_tokens=budget.synth_max_tokens,
    )
    usage["synth"] = _payload(synth_result)

    return {
        "final": synth_result.text,
        "decision": decision,
        "stages": stage_results,
        "usage": usage,
    }
