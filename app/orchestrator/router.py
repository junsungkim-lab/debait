import re

HIGH_RISK_KEYWORDS = [
    # 돈/법/보안/운영 리스크가 큰 것들
    "투자", "선물", "레버리지", "대출", "세금", "법", "소송", "의학", "약", "진단",
    "보안", "해킹", "취약점", "키", "비밀번호", "개인정보",
    "배포", "프로덕션", "장애",
]

def rule_based_gate(question: str) -> str:
    q = question.lower()
    if len(q) > 600:
        return "MULTI"
    if any(k in question for k in HIGH_RISK_KEYWORDS):
        return "MULTI"
    if re.search(r"```|def |class |import |SELECT |CREATE TABLE", question):
        return "MULTI"
    return "SIMPLE"
