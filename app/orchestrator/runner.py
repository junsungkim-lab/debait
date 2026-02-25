import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from . import prompts
from .router import rule_based_gate
from ..providers.anthropic_provider import AnthropicProvider
from ..providers.base import LLMResult
from ..providers.google_provider import GoogleProvider
from ..providers.groq_provider import GroqProvider
from ..providers.mistral_provider import MistralProvider
from ..providers.openai_provider import OpenAIProvider

PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "groq": GroqProvider(),
    "mistral": MistralProvider(),
}

PRICE_PER_1M_TOKENS = {
    "openai": (0.50, 1.50),
    "anthropic": (0.80, 4.00),
    "google": (0.35, 1.05),
    "groq": (0.10, 0.30),
    "mistral": (0.20, 0.60),
}


@dataclass
class Budget:
    max_usd: float = 0.10
    max_tokens_per_stage: int = 800
    synth_max_tokens: int = 1200


@dataclass
class ExecutionConfig:
    retries_per_stage: int = 1
    stage_timeout_sec: int = 75
    enable_dynamic_graph: bool = True
    enable_quality_matrix: bool = True
    quality_min_threshold: float = 3.0
    auto_refine_once: bool = True


def _split_model(full: str) -> tuple[str, str]:
    if ":" in full:
        p, m = full.split(":", 1)
        return p, m
    return "openai", full


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


def _contains_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _infer_dependencies(stages: List[Dict[str, str]]) -> Dict[int, List[int]]:
    deps: Dict[int, List[int]] = {}
    for idx, stage in enumerate(stages):
        if idx == 0:
            deps[idx] = []
            continue

        prompt = (stage.get("system_prompt") or "").lower()
        all_prev = _contains_any(
            prompt,
            ["all previous", "all prior", "모든 이전", "앞선", "이전 단계 전체", "all outputs"],
        )
        independent = _contains_any(prompt, ["independent", "standalone", "질문만", "독립적으로"])

        current_deps: list[int] = []
        if all_prev:
            current_deps = list(range(idx))
        else:
            for prev_idx in range(idx):
                prev_name = (stages[prev_idx].get("name") or "").strip().lower()
                if len(prev_name) >= 3 and prev_name in prompt:
                    current_deps.append(prev_idx)
            if not current_deps and not independent:
                current_deps = [idx - 1]
        deps[idx] = sorted(set(current_deps))
    return deps


def _topology_levels(num_nodes: int, deps: Dict[int, List[int]]) -> List[List[int]]:
    remaining = set(range(num_nodes))
    done = set()
    levels: List[List[int]] = []

    while remaining:
        ready = sorted(i for i in remaining if all(d in done for d in deps.get(i, [])))
        if not ready:
            # Cycle guard: fall back to deterministic order.
            ready = [min(remaining)]
        levels.append(ready)
        for i in ready:
            remaining.remove(i)
            done.add(i)
    return levels


def _quality_matrix(question: str, final_answer: str, stage_results: List[Dict[str, str]]) -> Dict[str, Any]:
    q_words = {w for w in question.lower().split() if len(w) >= 3}
    a_words = {w for w in final_answer.lower().split() if len(w) >= 3}
    overlap = len(q_words & a_words)
    overlap_ratio = overlap / max(1, len(q_words))

    accuracy = 2.5 + min(2.0, overlap_ratio * 2.0)
    if "uncertain" in final_answer.lower() or "불확실" in final_answer.lower():
        accuracy -= 0.5

    completeness = 2.0
    if len(final_answer) >= 220:
        completeness += 1.5
    if overlap_ratio >= 0.25:
        completeness += 1.0
    if overlap_ratio >= 0.45:
        completeness += 0.5

    consistency = 4.0
    contradiction_markers = ["but also not", "yes and no", "모순", "상충", "contradiction", "inconsistent"]
    if any(k in final_answer.lower() for k in contradiction_markers):
        consistency -= 1.5
    checker_notes = " ".join(s["text"] for s in stage_results if "checker" in s["name"].lower())
    if any(k in checker_notes.lower() for k in ["error", "모순", "inconsistent"]):
        consistency -= 0.8

    format_score = 2.5
    if "\n- " in final_answer or "\n1." in final_answer:
        format_score += 1.0
    if final_answer.rstrip().endswith((".", "!", "?", "다", "요")):
        format_score += 0.5
    if len(final_answer.splitlines()) >= 3:
        format_score += 0.5

    def clamp(v: float) -> float:
        return round(max(0.0, min(5.0, v)), 1)

    scores = {
        "accuracy": clamp(accuracy),
        "completeness": clamp(completeness),
        "consistency": clamp(consistency),
        "format": clamp(format_score),
    }
    scores["overall"] = round(sum(scores.values()) / 4, 2)
    return scores


def _payload(result: LLMResult, runtime: Dict[str, Any]) -> Dict[str, Any]:
    if result.cost_usd and result.cost_usd > 0:
        cost_usd = float(result.cost_usd)
    else:
        in_price, out_price = PRICE_PER_1M_TOKENS.get(result.provider or "openai", (0.50, 1.50))
        cost_usd = round(
            ((result.input_tokens * in_price) + (result.output_tokens * out_price)) / 1_000_000,
            6,
        )

    return {
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": runtime.get("latency_ms", 0),
        "retries": runtime.get("retries", 0),
        "status": runtime.get("status", "ok"),
    }


async def _call_with_resilience(
    *,
    provider: Any,
    api_key: str,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    cfg: ExecutionConfig,
) -> tuple[LLMResult | None, Dict[str, Any]]:
    attempts = cfg.retries_per_stage + 1
    last_error = ""
    total_latency_ms = 0

    for attempt in range(attempts):
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                provider.generate(
                    api_key=api_key,
                    model=model,
                    system=system,
                    user=user,
                    max_tokens=max_tokens,
                ),
                timeout=cfg.stage_timeout_sec,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            total_latency_ms += elapsed
            return result, {"latency_ms": total_latency_ms, "retries": attempt, "status": "ok"}
        except Exception as e:
            elapsed = int((time.perf_counter() - started) * 1000)
            total_latency_ms += elapsed
            last_error = f"{type(e).__name__}: {e}"
            if attempt < attempts - 1:
                await asyncio.sleep(min(0.8 * (2 ** attempt), 3.0))

    return None, {
        "latency_ms": total_latency_ms,
        "retries": max(0, attempts - 1),
        "status": "failed",
        "error": last_error,
    }


async def run_orchestrator(
    *,
    question: str,
    thread_summary: str,
    user_api_keys: Dict[str, str],
    stages: List[Dict[str, str]],  # [{"name": str, "system_prompt": str, "model": str}]
    synth_model: str,
    budget: Budget,
    use_llm_gate: bool = False,
    gate_model: str = "openai:gpt-4o-mini",
    execution_config: ExecutionConfig | None = None,
) -> Dict[str, Any]:
    cfg = execution_config or ExecutionConfig()

    if not stages:
        return {"final": "파이프라인 스테이지가 없습니다. Settings에서 스테이지를 추가해주세요."}

    decision = rule_based_gate(question)
    decision_reason = "rule-based gate"
    if use_llm_gate:
        gp, gm = _split_model(gate_model)
        gkey = user_api_keys.get(gp)
        gprov = PROVIDERS.get(gp)
        if gkey and gprov:
            gate_result, _ = await _call_with_resilience(
                provider=gprov,
                api_key=gkey,
                model=gm,
                system=prompts.GATE_SYSTEM,
                user=prompts.gate_user(thread_summary, question),
                max_tokens=5,
                cfg=cfg,
            )
            if gate_result:
                gt = gate_result.text.upper()
                if "MULTI" in gt:
                    decision = "MULTI"
                    decision_reason = "llm gate => MULTI"
                elif "SIMPLE" in gt:
                    decision = "SIMPLE"
                    decision_reason = "llm gate => SIMPLE"

    first_provider_name, first_model = _split_model(stages[0]["model"])
    first_provider = PROVIDERS.get(first_provider_name)
    first_key = user_api_keys.get(first_provider_name, "")
    if not first_provider or not first_key:
        return {"final": f"API Key가 없습니다: {first_provider_name}. Settings에서 등록해주세요."}

    stage_results_by_idx: Dict[int, Dict[str, str]] = {}
    usage: Dict[str, Any] = {}
    monitoring = {
        "decision_reason": decision_reason,
        "graph_levels": [],
        "total_latency_ms": 0,
        "total_cost_usd": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "stage_metrics": {},
        "budget_guard_triggered": False,
    }
    total_cost = 0.0

    deps = _infer_dependencies(stages) if cfg.enable_dynamic_graph else {i: [i - 1] for i in range(1, len(stages))}
    deps[0] = []

    if decision == "SIMPLE" or len(stages) == 1:
        first = stages[0]
        first_result, rt = await _call_with_resilience(
            provider=first_provider,
            api_key=first_key,
            model=first_model,
            system=first["system_prompt"],
            user=_build_stage_user_prompt(question, thread_summary, []),
            max_tokens=budget.max_tokens_per_stage,
            cfg=cfg,
        )
        if not first_result:
            return {"final": f"{first['name']} 실행 실패: {rt.get('error', 'unknown error')}"}
        usage[first["name"]] = _payload(first_result, rt)
        monitoring["total_cost_usd"] = usage[first["name"]].get("cost_usd", 0.0)
        monitoring["total_input_tokens"] = usage[first["name"]].get("input_tokens", 0)
        monitoring["total_output_tokens"] = usage[first["name"]].get("output_tokens", 0)
        monitoring["stage_metrics"][first["name"]] = rt
        monitoring["total_latency_ms"] = rt.get("latency_ms", 0)
        quality = _quality_matrix(question, first_result.text, [{"name": first["name"], "text": first_result.text}])
        return {
            "final": first_result.text,
            "decision": decision,
            "stages": [{"name": first["name"], "text": first_result.text}],
            "usage": usage,
            "quality": quality,
            "monitoring": monitoring,
        }

    levels = _topology_levels(len(stages), deps)
    monitoring["graph_levels"] = levels

    for level in levels:
        async def _run_stage(stage_idx: int) -> tuple[int, Dict[str, str], Dict[str, Any]]:
            stage = stages[stage_idx]
            provider_name, model_id = _split_model(stage["model"])
            provider = PROVIDERS.get(provider_name, first_provider)
            key = user_api_keys.get(provider_name) or first_key

            dep_results = [stage_results_by_idx[d] for d in deps.get(stage_idx, []) if d in stage_results_by_idx]
            if stage_idx == 0:
                prompt_user = _build_stage_user_prompt(question, thread_summary, [])
            else:
                prompt_user = _build_stage_user_prompt(question, "", dep_results)

            result, rt = await _call_with_resilience(
                provider=provider,
                api_key=key,
                model=model_id,
                system=stage["system_prompt"],
                user=prompt_user,
                max_tokens=budget.max_tokens_per_stage,
                cfg=cfg,
            )
            if not result:
                degraded_text = (
                    f"[{stage['name']} skipped due to transient failure]\n"
                    f"Reason: {rt.get('error', 'unknown error')}"
                )
                result = LLMResult(
                    text=degraded_text,
                    provider=provider_name,
                    model=model_id,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                )
            return stage_idx, {"name": stage["name"], "text": result.text}, _payload(result, rt)

        stage_outcomes = await asyncio.gather(*[_run_stage(i) for i in level])
        for idx, stage_data, stage_usage in stage_outcomes:
            stage_results_by_idx[idx] = stage_data
            usage[stage_data["name"]] = stage_usage
            monitoring["stage_metrics"][stage_data["name"]] = {
                "latency_ms": stage_usage.get("latency_ms", 0),
                "retries": stage_usage.get("retries", 0),
                "status": stage_usage.get("status", "ok"),
            }
            monitoring["total_latency_ms"] += int(stage_usage.get("latency_ms", 0) or 0)
            monitoring["total_input_tokens"] += int(stage_usage.get("input_tokens", 0) or 0)
            monitoring["total_output_tokens"] += int(stage_usage.get("output_tokens", 0) or 0)
            monitoring["total_cost_usd"] = round(
                float(monitoring["total_cost_usd"]) + float(stage_usage.get("cost_usd", 0.0) or 0.0), 6
            )
            total_cost += float(stage_usage.get("cost_usd", 0.0) or 0.0)

        if budget.max_usd > 0 and total_cost >= budget.max_usd:
            monitoring["budget_guard_triggered"] = True
            break

    ordered_stage_results = [stage_results_by_idx[i] for i in sorted(stage_results_by_idx.keys())]
    synth_provider_name, synth_model_id = _split_model(synth_model)
    synth_provider = PROVIDERS.get(synth_provider_name, first_provider)
    synth_key = user_api_keys.get(synth_provider_name) or first_key

    synth_result, synth_rt = await _call_with_resilience(
        provider=synth_provider,
        api_key=synth_key,
        model=synth_model_id,
        system=prompts.SYNTH_SYSTEM,
        user=_build_synth_user_prompt(question, ordered_stage_results),
        max_tokens=budget.synth_max_tokens,
        cfg=cfg,
    )
    if not synth_result:
        return {"final": f"Synth 실행 실패: {synth_rt.get('error', 'unknown error')}"}

    usage["synth"] = _payload(synth_result, synth_rt)
    monitoring["stage_metrics"]["synth"] = {
        "latency_ms": synth_rt.get("latency_ms", 0),
        "retries": synth_rt.get("retries", 0),
        "status": synth_rt.get("status", "ok"),
    }
    monitoring["total_latency_ms"] += int(synth_rt.get("latency_ms", 0) or 0)
    monitoring["total_input_tokens"] += int(usage["synth"].get("input_tokens", 0) or 0)
    monitoring["total_output_tokens"] += int(usage["synth"].get("output_tokens", 0) or 0)
    monitoring["total_cost_usd"] = round(
        float(monitoring["total_cost_usd"]) + float(usage["synth"].get("cost_usd", 0.0) or 0.0), 6
    )

    final_text = synth_result.text
    quality = _quality_matrix(question, final_text, ordered_stage_results)
    refined = False

    if (
        cfg.enable_quality_matrix
        and cfg.auto_refine_once
        and min(quality["accuracy"], quality["completeness"], quality["consistency"], quality["format"]) < cfg.quality_min_threshold
    ):
        refine_user = (
            f"Question:\n{question}\n\n"
            f"Current answer:\n{final_text}\n\n"
            f"Quality scores:\n{quality}\n\n"
            "Improve weak dimensions while keeping facts conservative and format clean."
        )
        refined_result, refined_rt = await _call_with_resilience(
            provider=synth_provider,
            api_key=synth_key,
            model=synth_model_id,
            system=prompts.QUALITY_REFINE_SYSTEM,
            user=refine_user,
            max_tokens=budget.synth_max_tokens,
            cfg=cfg,
        )
        if refined_result and refined_result.text.strip():
            candidate_quality = _quality_matrix(question, refined_result.text, ordered_stage_results)
            if candidate_quality["overall"] >= quality["overall"]:
                final_text = refined_result.text
                quality = candidate_quality
                refined = True
                usage["quality_refine"] = _payload(refined_result, refined_rt)
                monitoring["stage_metrics"]["quality_refine"] = {
                    "latency_ms": refined_rt.get("latency_ms", 0),
                    "retries": refined_rt.get("retries", 0),
                    "status": refined_rt.get("status", "ok"),
                }
                monitoring["total_latency_ms"] += int(refined_rt.get("latency_ms", 0) or 0)
                monitoring["total_input_tokens"] += int(usage["quality_refine"].get("input_tokens", 0) or 0)
                monitoring["total_output_tokens"] += int(usage["quality_refine"].get("output_tokens", 0) or 0)
                monitoring["total_cost_usd"] = round(
                    float(monitoring["total_cost_usd"]) + float(usage["quality_refine"].get("cost_usd", 0.0) or 0.0),
                    6,
                )

    quality["refined"] = refined

    return {
        "final": final_text,
        "decision": decision,
        "stages": ordered_stage_results,
        "usage": usage,
        "quality": quality,
        "monitoring": monitoring,
    }
