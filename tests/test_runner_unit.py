"""
Unit tests for app.orchestrator.runner — pure functions
(Features #2 복원력 설정, #3 동적 그래프, #4 품질매트릭, #5 비용모니터링)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.orchestrator.runner import (
    _split_model,
    _build_stage_user_prompt,
    _build_synth_user_prompt,
    _contains_any,
    _infer_dependencies,
    _topology_levels,
    _quality_matrix,
    _payload,
    Budget,
    ExecutionConfig,
)
from app.providers.base import LLMResult


# ═══════════════════════════════════════════════════════════════
# _split_model
# ═══════════════════════════════════════════════════════════════
class TestSplitModel:
    def test_with_colon(self):
        assert _split_model("openai:gpt-4o") == ("openai", "gpt-4o")

    def test_without_colon_defaults_to_openai(self):
        assert _split_model("gpt-4o") == ("openai", "gpt-4o")

    def test_anthropic_prefix(self):
        assert _split_model("anthropic:claude-3-5-sonnet") == ("anthropic", "claude-3-5-sonnet")

    def test_multiple_colons_only_first_split(self):
        p, m = _split_model("openai:gpt-4:turbo")
        assert p == "openai"
        assert m == "gpt-4:turbo"


# ═══════════════════════════════════════════════════════════════
# _build_stage_user_prompt / _build_synth_user_prompt
# ═══════════════════════════════════════════════════════════════
class TestPromptBuilders:
    def test_stage_no_prev_no_summary(self):
        out = _build_stage_user_prompt("Q?", "", [])
        assert "Q?" in out
        assert "Thread context" not in out

    def test_stage_with_thread_summary(self):
        out = _build_stage_user_prompt("Q?", "prev context", [])
        assert "Thread context" in out
        assert "prev context" in out

    def test_stage_with_prev_results(self):
        prev = [{"name": "Solver", "text": "answer A"}]
        out = _build_stage_user_prompt("Q?", "", prev)
        assert "Solver" in out
        assert "answer A" in out

    def test_synth_prompt_includes_all_stages(self):
        stages = [
            {"name": "Solver", "text": "sol"},
            {"name": "Critic", "text": "crit"},
        ]
        out = _build_synth_user_prompt("Q?", stages)
        assert "Solver" in out
        assert "Critic" in out
        assert "Final answer:" in out


# ═══════════════════════════════════════════════════════════════
# _contains_any
# ═══════════════════════════════════════════════════════════════
class TestContainsAny:
    def test_found(self):
        assert _contains_any("all previous stages", ["all previous"])

    def test_not_found(self):
        assert not _contains_any("review the outputs", ["all previous"])

    def test_case_insensitive(self):
        assert _contains_any("ALL PREVIOUS", ["all previous"])

    def test_empty_keywords(self):
        assert not _contains_any("some text", [])


# ═══════════════════════════════════════════════════════════════
# Feature #3 — _infer_dependencies
# ═══════════════════════════════════════════════════════════════
class TestInferDependencies:
    def _stage(self, name, prompt=""):
        return {"name": name, "system_prompt": prompt, "model": "openai:gpt-4o-mini"}

    def test_single_stage_no_deps(self):
        stages = [self._stage("Solver")]
        deps = _infer_dependencies(stages)
        assert deps == {0: []}

    def test_sequential_default(self):
        stages = [
            self._stage("Solver", "Answer the question."),
            self._stage("Critic", "Critique the answer."),
            self._stage("Synth", "Combine everything."),
        ]
        deps = _infer_dependencies(stages)
        assert deps[0] == []
        assert deps[1] == [0]   # Critic → Solver (직전)
        assert deps[2] == [1]   # Synth → Critic (직전)

    def test_all_previous_keyword(self):
        stages = [
            self._stage("A", "Answer."),
            self._stage("B", "Check."),
            self._stage("C", "Use all previous outputs to synthesize."),
        ]
        deps = _infer_dependencies(stages)
        assert deps[2] == [0, 1]

    def test_korean_all_previous(self):
        stages = [
            self._stage("A", "답변."),
            self._stage("B", "검증."),
            self._stage("C", "모든 이전 단계를 참조해서 최종 답변 작성."),
        ]
        deps = _infer_dependencies(stages)
        assert deps[2] == [0, 1]

    def test_independent_keyword(self):
        stages = [
            self._stage("A", "Answer."),
            self._stage("B", "Independent analysis of the question only."),
        ]
        deps = _infer_dependencies(stages)
        # independent → 빈 의존성 (직전 단계 자동 추가 없음)
        # 1글자 스테이지명("a")이 "analysis" 등에 substring 오매칭되지 않아야 함
        assert deps[1] == []

    def test_name_reference_in_prompt(self):
        stages = [
            self._stage("solver", "Answer."),
            self._stage("critic", "Check."),
            self._stage("Refiner", "Take solver output and improve it."),
        ]
        deps = _infer_dependencies(stages)
        # "solver" 이름이 Refiner 프롬프트에 포함됨
        assert 0 in deps[2]

    def test_first_stage_always_empty(self):
        stages = [self._stage("A", "all previous outputs")]
        deps = _infer_dependencies(stages)
        assert deps[0] == []


# ═══════════════════════════════════════════════════════════════
# Feature #3 — _topology_levels
# ═══════════════════════════════════════════════════════════════
class TestTopologyLevels:
    def test_linear_chain(self):
        deps = {0: [], 1: [0], 2: [1]}
        levels = _topology_levels(3, deps)
        assert levels == [[0], [1], [2]]

    def test_all_independent_parallel(self):
        deps = {0: [], 1: [], 2: []}
        levels = _topology_levels(3, deps)
        assert levels == [[0, 1, 2]]

    def test_diamond_pattern(self):
        # 0 → 1,2 → 3
        deps = {0: [], 1: [0], 2: [0], 3: [1, 2]}
        levels = _topology_levels(4, deps)
        assert levels[0] == [0]
        assert set(levels[1]) == {1, 2}
        assert levels[2] == [3]

    def test_single_node(self):
        levels = _topology_levels(1, {0: []})
        assert levels == [[0]]

    def test_cycle_guard_does_not_hang(self):
        # 순환 의존성도 무한루프 없이 완료
        deps = {0: [1], 1: [0]}
        levels = _topology_levels(2, deps)
        total = sum(len(l) for l in levels)
        assert total == 2

    def test_covers_all_nodes(self):
        deps = {0: [], 1: [0], 2: [0], 3: [1, 2], 4: [3]}
        levels = _topology_levels(5, deps)
        all_nodes = [n for level in levels for n in level]
        assert sorted(all_nodes) == [0, 1, 2, 3, 4]


# ═══════════════════════════════════════════════════════════════
# Feature #4 — _quality_matrix
# ═══════════════════════════════════════════════════════════════
class TestQualityMatrix:
    def _run(self, question, answer, stage_results=None):
        return _quality_matrix(question, answer, stage_results or [])

    def test_returns_all_keys(self):
        q = _quality_matrix("What is Python?", "Python is a programming language.", [])
        for key in ("accuracy", "completeness", "consistency", "format", "overall"):
            assert key in q

    def test_all_scores_in_range(self):
        q = _quality_matrix("Explain Redis caching strategy.", "Redis is fast.", [])
        for key in ("accuracy", "completeness", "consistency", "format"):
            assert 0.0 <= q[key] <= 5.0

    def test_overall_is_average(self):
        q = _quality_matrix("What is Python?", "Python is a programming language.", [])
        expected = round((q["accuracy"] + q["completeness"] + q["consistency"] + q["format"]) / 4, 2)
        assert q["overall"] == expected

    def test_long_answer_higher_completeness(self):
        short = "Python is good."
        long_ans = ("Python is a high-level, interpreted programming language known for "
                    "its readability and versatility. It supports multiple paradigms including "
                    "object-oriented, functional, and procedural. It is widely used in data "
                    "science, web development, and automation scripting.")
        q_short = _quality_matrix("What is Python?", short, [])
        q_long  = _quality_matrix("What is Python?", long_ans, [])
        assert q_long["completeness"] >= q_short["completeness"]

    def test_uncertain_keyword_reduces_accuracy(self):
        certain   = "Python is a high level programming language used widely."
        uncertain = "Python is uncertain as a high level language honestly."
        q_c = _quality_matrix("What is Python?", certain, [])
        q_u = _quality_matrix("What is Python?", uncertain, [])
        assert q_u["accuracy"] < q_c["accuracy"]

    def test_contradiction_marker_reduces_consistency(self):
        normal    = "Python is great for data science applications."
        contradicted = "Python is great but also not suitable for any tasks and inconsistent."
        q_n = _quality_matrix("Python?", normal, [])
        q_c = _quality_matrix("Python?", contradicted, [])
        assert q_c["consistency"] < q_n["consistency"]

    def test_checker_error_reduces_consistency(self):
        stage_with_error = [{"name": "checker", "text": "Found error in logic step 3."}]
        stage_clean      = [{"name": "checker", "text": "All checks passed."}]
        q_err   = _quality_matrix("Q?", "Answer.", stage_with_error)
        q_clean = _quality_matrix("Q?", "Answer.", stage_clean)
        assert q_err["consistency"] < q_clean["consistency"]

    def test_bullet_list_improves_format(self):
        plain  = "First do A. Then do B. Then do C."
        listed = "Steps:\n- Do A\n- Do B\n- Do C"
        q_p = _quality_matrix("How to do it?", plain, [])
        q_l = _quality_matrix("How to do it?", listed, [])
        assert q_l["format"] >= q_p["format"]

    def test_numbered_list_improves_format(self):
        answer = "Here are the steps:\n1. Install Python\n2. Create a virtualenv\n3. Install packages"
        q = _quality_matrix("How to setup Python?", answer, [])
        assert q["format"] > 2.5

    def test_proper_ending_improves_format(self):
        ends_well  = "This is the final answer."
        ends_badly = "This is the final answer"
        q_w = _quality_matrix("Q?", ends_well, [])
        q_b = _quality_matrix("Q?", ends_badly, [])
        assert q_w["format"] >= q_b["format"]

    def test_overlap_ratio_improves_completeness(self):
        # 질문 단어가 답변에 많이 포함될수록 completeness 상승
        question = "explain python caching implementation strategies"
        high_overlap = ("python caching implementation can use several strategies "
                        "like redis memcached or local dict based explain each")
        low_overlap = "There are many ways to speed things up in software."
        q_high = _quality_matrix(question, high_overlap, [])
        q_low  = _quality_matrix(question, low_overlap, [])
        assert q_high["completeness"] >= q_low["completeness"]

    def test_empty_answer(self):
        q = _quality_matrix("What is Python?", "", [])
        assert q["overall"] >= 0.0


# ═══════════════════════════════════════════════════════════════
# Feature #5 — _payload (비용 계산)
# ═══════════════════════════════════════════════════════════════
class TestPayload:
    def _make_result(self, provider="openai", model="gpt-4o-mini",
                     input_tokens=100, output_tokens=50, cost_usd=0.0):
        return LLMResult(
            text="answer",
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )

    def test_uses_provider_cost_when_set(self):
        result = self._make_result(cost_usd=0.005)
        rt = {"latency_ms": 100, "retries": 0, "status": "ok"}
        p = _payload(result, rt)
        assert p["cost_usd"] == 0.005

    def test_calculates_cost_when_zero(self):
        result = self._make_result(provider="openai", input_tokens=1_000_000, output_tokens=0, cost_usd=0.0)
        rt = {"latency_ms": 200, "retries": 0, "status": "ok"}
        p = _payload(result, rt)
        # openai: in=0.50/1M → 1M tokens = $0.50
        assert abs(p["cost_usd"] - 0.50) < 0.0001

    def test_calculates_output_cost(self):
        result = self._make_result(provider="openai", input_tokens=0, output_tokens=1_000_000, cost_usd=0.0)
        rt = {"latency_ms": 200, "retries": 0, "status": "ok"}
        p = _payload(result, rt)
        # openai: out=1.50/1M → 1M tokens = $1.50
        assert abs(p["cost_usd"] - 1.50) < 0.0001

    def test_anthropic_pricing(self):
        result = self._make_result(provider="anthropic", input_tokens=1_000_000, output_tokens=0, cost_usd=0.0)
        rt = {"latency_ms": 0, "retries": 0, "status": "ok"}
        p = _payload(result, rt)
        assert abs(p["cost_usd"] - 0.80) < 0.0001

    def test_unknown_provider_falls_back_to_openai_pricing(self):
        result = self._make_result(provider="unknown_llm", input_tokens=1_000_000, output_tokens=0, cost_usd=0.0)
        rt = {"latency_ms": 0, "retries": 0, "status": "ok"}
        p = _payload(result, rt)
        # fallback = openai pricing (0.50, 1.50)
        assert abs(p["cost_usd"] - 0.50) < 0.0001

    def test_runtime_fields_included(self):
        result = self._make_result()
        rt = {"latency_ms": 350, "retries": 2, "status": "ok"}
        p = _payload(result, rt)
        assert p["latency_ms"] == 350
        assert p["retries"] == 2
        assert p["status"] == "ok"

    def test_all_expected_keys_present(self):
        result = self._make_result()
        rt = {"latency_ms": 0, "retries": 0, "status": "ok"}
        p = _payload(result, rt)
        for key in ("text", "provider", "model", "input_tokens", "output_tokens",
                    "cost_usd", "latency_ms", "retries", "status"):
            assert key in p


# ═══════════════════════════════════════════════════════════════
# Feature #2 — ExecutionConfig defaults
# ═══════════════════════════════════════════════════════════════
class TestExecutionConfig:
    def test_default_values(self):
        cfg = ExecutionConfig()
        assert cfg.retries_per_stage == 1
        assert cfg.stage_timeout_sec == 75
        assert cfg.enable_dynamic_graph is True
        assert cfg.enable_quality_matrix is True
        assert cfg.quality_min_threshold == 3.0
        assert cfg.auto_refine_once is True

    def test_custom_values(self):
        cfg = ExecutionConfig(retries_per_stage=3, stage_timeout_sec=30, enable_dynamic_graph=False)
        assert cfg.retries_per_stage == 3
        assert cfg.stage_timeout_sec == 30
        assert cfg.enable_dynamic_graph is False


class TestBudget:
    def test_default_values(self):
        b = Budget()
        assert b.max_usd == 0.10
        assert b.max_tokens_per_stage == 800
        assert b.synth_max_tokens == 1200
