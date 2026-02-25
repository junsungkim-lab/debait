"""
Unit tests for app.orchestrator.clarifier (Feature #1: 요청 명확화)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.orchestrator.clarifier import analyze_request_clarity, ClarificationResult


class TestClarificationResult:
    def test_dataclass_fields(self):
        r = ClarificationResult(score=0.5, reasons=["r1"], questions=["q1"])
        assert r.score == 0.5
        assert r.reasons == ["r1"]
        assert r.questions == ["q1"]


class TestAnalyzeRequestClarity:
    # ── 기본 반환 타입 ──────────────────────────────────────────────
    def test_returns_clarification_result(self):
        result = analyze_request_clarity("hello")
        assert isinstance(result, ClarificationResult)

    def test_score_in_range(self):
        for q in ["", "hi", "fix this code", "이거 고쳐줘", "이거 뭔데 이거 뭐냐? 이거?",
                  "Please implement a Redis cache module for this Python FastAPI application"]:
            r = analyze_request_clarity(q)
            assert 0.0 <= r.score <= 1.0, f"score out of range for: {q!r}"

    def test_questions_always_two(self):
        for q in ["", "short", "A longer question about implementing a system"]:
            r = analyze_request_clarity(q)
            assert len(r.questions) == 2

    def test_reasons_capped_at_three(self):
        # worst-case: short + deictic + multiple ? + no goal + no format → all reasons fire
        r = analyze_request_clarity("이거? 저거?")
        assert len(r.reasons) <= 3

    # ── 짧은 요청 (+0.35) ───────────────────────────────────────────
    def test_short_question_raises_score(self):
        short = "help"  # 4자
        long  = "Please help me implement and compare two caching strategies for Redis"
        r_short = analyze_request_clarity(short)
        r_long  = analyze_request_clarity(long)
        assert r_short.score > r_long.score

    def test_exactly_20_chars_not_short(self):
        # 20자 정확히는 short 조건(< 20) 미해당
        q = "a" * 20
        r = analyze_request_clarity(q)
        assert 0.35 not in [r.score]  # 단독 short 점수만 없어야 함 (다른 규칙 복합 제외)

    def test_19_chars_is_short(self):
        q = "a" * 19
        r_19 = analyze_request_clarity(q)
        r_20 = analyze_request_clarity("a" * 20)
        assert r_19.score > r_20.score  # 19자는 short 조건 해당

    # ── 복수 물음표 (+0.15) ─────────────────────────────────────────
    def test_multiple_question_marks_raises_score(self):
        # single: 1 question mark, no deictic, has goal hint "design", no format → +0.10
        single = "What is the best caching strategy for production system design?"
        # multi: 3 question marks → +0.15, has goal hint "implement", no format → +0.10
        multi  = "What should we implement? Which approach is better? Why so?"
        r_s = analyze_request_clarity(single)
        r_m = analyze_request_clarity(multi)
        assert r_m.score > r_s.score

    def test_fullwidth_question_mark_counted(self):
        q = "어떻게 하나요？ 이건 왜요？ 뭔가요？"
        r = analyze_request_clarity(q)
        assert r.score > 0  # 복수 ？ 감지

    # ── 지시어 (+0.25) ─────────────────────────────────────────────
    def test_english_deictic_this(self):
        q = "Can you fix this broken function in the module"
        r = analyze_request_clarity(q)
        reason_texts = " ".join(r.reasons)
        assert "지시어" in reason_texts

    def test_korean_deictic_이거(self):
        q = "이거 어떻게 고치면 되는지 코드로 설명해줘 좀 제발"
        r = analyze_request_clarity(q)
        reason_texts = " ".join(r.reasons)
        assert "지시어" in reason_texts

    def test_no_deictic_no_reason(self):
        q = "Please implement a Redis cache module for FastAPI with TTL support"
        r = analyze_request_clarity(q)
        assert not any("지시어" in reason for reason in r.reasons)

    # ── 목표 미명시 (+0.15) ─────────────────────────────────────────
    def test_no_goal_hint_adds_score(self):
        no_goal = "I need something done about the performance issue in production"
        with_goal = "Please review and fix the performance issue in production"
        r_ng = analyze_request_clarity(no_goal)
        r_wg = analyze_request_clarity(with_goal)
        assert r_ng.score > r_wg.score

    def test_korean_goal_hint_구현(self):
        q = "로그인 기능을 구현해주세요. 최대한 자세하게 설명과 함께 작성 부탁드립니다."
        r = analyze_request_clarity(q)
        assert not any("작업 유형" in reason for reason in r.reasons)

    # ── 출력 형식 미명시 (+0.10) ────────────────────────────────────
    def test_format_hint_markdown_reduces_score(self):
        with_fmt = "Please review the authentication module and provide output as markdown"
        without_fmt = "Please review the authentication module thoroughly and in detail"
        r_wf = analyze_request_clarity(with_fmt)
        r_wo = analyze_request_clarity(without_fmt)
        assert r_wf.score < r_wo.score

    def test_format_hint_코드_reduces_score(self):
        # 한국어 조사 없이 "코드" 단독 사용 → \b 경계 매칭
        q = "로그인 기능을 구현해서 코드 예시로 알려주세요. 자세하게 설명 부탁드립니다."
        r = analyze_request_clarity(q)
        assert not any("출력 형식" in reason for reason in r.reasons)

    # ── 점수 상한 1.0 ───────────────────────────────────────────────
    def test_score_capped_at_1(self):
        # 모든 패널티를 최대로 트리거하는 입력
        r = analyze_request_clarity("이거? 저거?")  # short + deictic + multi-? + no goal + no format
        assert r.score <= 1.0

    # ── 빈 입력 / None 처리 ─────────────────────────────────────────
    def test_empty_string(self):
        r = analyze_request_clarity("")
        assert isinstance(r, ClarificationResult)
        assert r.score >= 0.0

    def test_whitespace_only(self):
        r = analyze_request_clarity("   ")
        assert isinstance(r, ClarificationResult)

    # ── 임계값 기준 확인 (≥0.55 → 사전질문 필요) ───────────────────
    def test_clear_specific_question_below_threshold(self):
        q = "Please implement a Redis cache module in Python with TTL support. Output as markdown code."
        r = analyze_request_clarity(q)
        assert r.score < 0.55, f"Specific question should be below threshold, got {r.score}"

    def test_vague_short_deictic_above_threshold(self):
        # short(0.35) + deictic(0.25) + no goal(0.15) = 0.75 → 임계값 초과
        q = "fix this bug"  # short + deictic(this) + no explicit goal
        r = analyze_request_clarity(q)
        assert r.score >= 0.55, f"Vague question should exceed threshold, got {r.score}"
