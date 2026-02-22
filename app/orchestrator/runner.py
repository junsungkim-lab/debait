from dataclasses import dataclass
from typing import Any, Dict
from . import prompts
from .router import rule_based_gate
from ..providers.openai_provider import OpenAIProvider
from ..providers.anthropic_provider import AnthropicProvider
from ..providers.base import LLMResult

PROVIDERS = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
}

@dataclass
class Budget:
    max_rounds: int = 1
    max_usd: float = 0.03
    critic_max_tokens: int = 200
    checker_max_tokens: int = 200
    solver_max_tokens: int = 500
    synth_max_tokens: int = 700

def _split_model(full: str):
    # format: "openai:gpt-4o-mini" or "anthropic:claude-3-5-sonnet-latest"
    if ":" in full:
        p, m = full.split(":", 1)
        return p, m
    return "openai", full

async def run_orchestrator(
    *,
    question: str,
    thread_summary: str,
    user_api_keys: Dict[str, str],  # provider -> api_key
    models: Dict[str, str],         # role -> provider:model
    budget: Budget,
    use_llm_gate: bool = False,
) -> Dict[str, Any]:
    def _result_payload(result: LLMResult) -> Dict[str, Any]:
        return {
            "text": result.text,
            "provider": result.provider,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
        }

    # Decide SIMPLE/MULTI
    decision = rule_based_gate(question)
    if use_llm_gate:
        gate_provider, gate_model = _split_model(models.get("gate", "openai:gpt-4o-mini"))
        gate_key = user_api_keys.get(gate_provider)
        if gate_key:
            prov = PROVIDERS[gate_provider]
            g = await prov.generate(
                api_key=gate_key,
                model=gate_model,
                system=prompts.GATE_SYSTEM,
                user=prompts.gate_user(thread_summary, question),
                max_tokens=5,
            )
            if "MULTI" in g.text.upper():
                decision = "MULTI"
            elif "SIMPLE" in g.text.upper():
                decision = "SIMPLE"

    # Solver always required
    solver_provider, solver_model = _split_model(models.get("solver", "openai:gpt-4o-mini"))
    solver_key = user_api_keys.get(solver_provider)
    if not solver_key:
        return {"final": "웹앱에서 Solver용 API Key를 먼저 등록해줘. (openai 또는 anthropic)"}

    solver = PROVIDERS[solver_provider]
    a = await solver.generate(
        api_key=solver_key,
        model=solver_model,
        system=prompts.SOLVER_SYSTEM,
        user=f"""Thread summary:
{thread_summary}

Q: {question}

Answer:""",
        max_tokens=budget.solver_max_tokens,
    )

    if decision == "SIMPLE":
        solver_result = _result_payload(a)
        return {
            "final": a.text,
            "solver": a.text,
            "decision": decision,
            "usage": {"solver": solver_result},
        }

    # Critic (optional)
    critic_provider, critic_model = _split_model(models.get("critic", models.get("solver", "openai:gpt-4o-mini")))
    critic_key = user_api_keys.get(critic_provider, solver_key)
    critic = PROVIDERS.get(critic_provider, solver)
    b = await critic.generate(
        api_key=critic_key,
        model=critic_model,
        system=prompts.CRITIC_SYSTEM,
        user=f"""Question: {question}

Solver answer:
{a.text}

Critique:""",
        max_tokens=budget.critic_max_tokens,
    )

    # Checker (optional)
    checker_provider, checker_model = _split_model(models.get("checker", models.get("solver", "openai:gpt-4o-mini")))
    checker_key = user_api_keys.get(checker_provider, solver_key)
    checker = PROVIDERS.get(checker_provider, solver)
    c = await checker.generate(
        api_key=checker_key,
        model=checker_model,
        system=prompts.CHECKER_SYSTEM,
        user=f"""Question: {question}

Solver:
{a.text}

Critic:
{b.text}

Checks & fixes:""",
        max_tokens=budget.checker_max_tokens,
    )

    # Synth
    synth_provider, synth_model = _split_model(models.get("synth", models.get("solver", "openai:gpt-4o-mini")))
    synth_key = user_api_keys.get(synth_provider, solver_key)
    synth = PROVIDERS.get(synth_provider, solver)
    final = await synth.generate(
        api_key=synth_key,
        model=synth_model,
        system=prompts.SYNTH_SYSTEM,
        user=f"""Q: {question}

Solver:
{a.text}

Critic:
{b.text}

Checker:
{c.text}

Final answer:""",
        max_tokens=budget.synth_max_tokens,
    )

    usage = {
        "solver": _result_payload(a),
        "critic": _result_payload(b),
        "checker": _result_payload(c),
        "synth": _result_payload(final),
    }

    return {
        "final": final.text,
        "decision": decision,
        "solver": a.text,
        "critic": b.text,
        "checker": c.text,
        "usage": usage,
    }
