# AI 멀티모델 단톡방 (BYOK) WebApp + Telegram Webhook MVP (FastAPI)

이 프로젝트는 **웹앱이 본체**(BYOK 키 관리, 대화 로그, 비용/토큰 계측, 오케스트레이터)이고,
외부 입력 채널은 **Telegram Bot Webhook**으로 연결하는 최소 MVP 템플릿입니다.

## 구성 요약
- WebApp: FastAPI + Jinja2 (간단한 로그인/대시보드/키등록/대화로그)
- Telegram: Webhook(HTTPS) → /tg/{WEBHOOK_SECRET}
- Orchestrator: Gate(저가) → Solver → (Critic/Checker 조건부) → Synth
- BYOK: 사용자별 OpenAI/Anthropic 키 저장(서버 MASTER_KEY로 암호화)
- DB: SQLite (로컬 파일)
- 비동기 처리: FastAPI BackgroundTasks (MVP용)

> ⚠️ 운영 환경에서는 Redis 큐(BullMQ/Celery/RQ) + KMS(Secrets Manager)로 강화 권장.

---

## 빠른 시작

### 1) Python 설치
- Python 3.11+ 권장

### 2) 설치
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3) 환경변수 설정
`.env.example`을 복사해서 `.env` 만들고 값을 채우세요.

```bash
cp .env.example .env
```

필수:
- `TELEGRAM_BOT_TOKEN` : BotFather에서 발급받은 봇 토큰
- `WEBHOOK_SECRET` : 임의의 긴 문자열(웹훅 URL 비밀 경로)
- `MASTER_KEY` : 32-byte urlsafe base64 (아래 생성 명령 참고)
- `BASE_URL` : 외부에서 접근 가능한 https URL (예: https://api.example.com)

MASTER_KEY 생성:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 4) 실행
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5) Telegram Webhook 설정
ngrok 같은 터널을 써도 되고, 실제 도메인/HTTPS를 써도 됩니다.

Webhook URL:
`{BASE_URL}/tg/{WEBHOOK_SECRET}`

설정(한 번만):
```bash
python scripts/set_webhook.py
```

해제:
```bash
python scripts/delete_webhook.py
```

---

## 사용 방법(기본 플로우)
1) 웹앱 접속 → 회원가입/로그인
2) Dashboard에서 BYOK 키(OpenAI/Anthropic 중 하나라도) 등록
3) Dashboard에서 **Telegram 연결 코드** 생성
4) Telegram에서 봇에게 `/start` → 안내대로 연결 코드 전송
5) 이제 Telegram에 질문을 보내면 오케스트레이터가 답하고, 결과가 Telegram으로 돌아옵니다.

---

## 오케스트레이터 정책(기본)
- Gate: cheap 라우팅(현재는 규칙 기반 + 간단한 LLM Gate 옵션 제공)
- Critic/Checker: 불확실/고위험 키워드/긴 코드 등일 때만 조건부 실행
- 출력 토큰 상한:
  - Critic/Checker: 200
  - Synth: 700
- 라운드 상한: 2 (MVP 기본 1)

---

## 파일 구조
```
app/
  main.py
  settings.py
  db.py
  models.py
  crypto.py
  telegram.py
  orchestrator/
    prompts.py
    router.py
    runner.py
  providers/
    base.py
    openai_provider.py
    anthropic_provider.py
  templates/
    base.html
    login.html
    register.html
    dashboard.html
    conversations.html
scripts/
  set_webhook.py
  delete_webhook.py
.env.example
requirements.txt
```

---

## 주의사항
- 이 템플릿은 **MVP/학습용**입니다. 실서비스는 반드시:
  - HTTPS 고정, webhook secret 검증 강화
  - 키 저장은 KMS/Secret Manager 사용
  - 큐/워커 분리(웹서버는 빠르게 200 OK 반환)
  - 요청/응답 로그의 PII 마스킹
  - 사용량/과금 방지(레이트 리밋, 쿼터)
