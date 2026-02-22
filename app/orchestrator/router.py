import re

SIMPLE_PATTERNS = [
    r"^(안녕|hi|hello|hey|ㅎㅇ|하이)[!?.\s]*$",
    r"^(고마워|감사|thank)[!?.\s]*$",
    r"^(몇\s*시|what\s*time|오늘\s*날씨)[^가-힣a-z]*$",
]

def rule_based_gate(question: str) -> str:
    q = question.strip()
    # 명백한 단순 인삿말·단답형만 SIMPLE, 나머지는 전부 MULTI
    if len(q) < 20 and any(re.search(p, q, re.IGNORECASE) for p in SIMPLE_PATTERNS):
        return "SIMPLE"
    return "MULTI"
