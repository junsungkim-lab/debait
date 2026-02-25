import re
from dataclasses import dataclass


@dataclass
class ClarificationResult:
    score: float
    reasons: list[str]
    questions: list[str]


_DEICTIC_PATTERNS = [
    r"\b(it|this|that|these|those)\b",
    r"(이거|그거|저거|이것|그것|저것|요거)",
]

_GOAL_HINTS = [
    "implement", "fix", "compare", "plan", "design", "debug", "review",
    "구현", "수정", "비교", "계획", "설계", "디버그", "리뷰",
]


def analyze_request_clarity(question: str) -> ClarificationResult:
    q = (question or "").strip()
    q_lower = q.lower()
    reasons: list[str] = []
    score = 0.0

    if len(q) < 20:
        score += 0.35
        reasons.append("요청이 짧아 목표/범위 해석 여지가 큽니다.")

    if len(re.findall(r"[?？]", q)) >= 2:
        score += 0.15
        reasons.append("질문이 복수 개라 우선순위가 모호합니다.")

    if any(re.search(p, q_lower) for p in _DEICTIC_PATTERNS):
        score += 0.25
        reasons.append("지시어(이거/that 등)가 있어 대상이 불명확할 수 있습니다.")

    if not any(h in q_lower for h in _GOAL_HINTS):
        score += 0.15
        reasons.append("원하는 작업 유형(구현/비교/리뷰 등)이 명시되지 않았습니다.")

    if not re.search(r"\b(json|table|markdown|코드|문서|요약|리스트)\b", q_lower):
        score += 0.10
        reasons.append("원하는 출력 형식이 명확하지 않습니다.")

    score = min(1.0, round(score, 2))

    questions = [
        "가장 중요한 목표 1가지를 먼저 알려주세요. (예: 속도 최적화, 정확도, 비용 절감)",
        "제약 조건을 알려주세요. (예: 시간, 예산, 기술 스택, 변경 가능 범위)",
        "원하는 출력 형식을 알려주세요. (예: 체크리스트, 코드 패치, 표, 단계별 가이드)",
    ]
    return ClarificationResult(score=score, reasons=reasons[:3], questions=questions[:2])
