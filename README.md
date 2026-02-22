# Debait — AI 집단지성 오케스트레이터

여러 AI 모델이 **역할 기반 토론**을 통해 하나의 최적 답변을 만드는 웹 기반 멀티 에이전트 시스템입니다.

단순 챗봇이 아니라, AI들이 실제로 서로 검토하고 반박하며 답을 정제합니다.

```
질문 입력
   ↓
Solver  → 해결안 제시
   ↓
Critic  → 약점 · 리스크 지적
   ↓
Checker → 논리 검증 · 수정
   ↓
Synth   → 최종 합의 답변 생성
```

---

## 주요 기능

- **웹 채팅 인터페이스** — 로그인 없이 바로 질문
- **AI 토론 시각화** — Solver / Critic / Checker / Synth 각 단계 결과 표시
- **BYOK** (Bring Your Own Key) — OpenAI · Anthropic API 키를 직접 등록해서 사용
- **Telegram 연동** — 웹앱과 연결 후 Telegram에서도 동일하게 사용 가능
- **대화 기록** — 웹 · Telegram 전체 대화 저장 및 조회
- **키 암호화 저장** — API 키는 Fernet(AES-128)으로 암호화 후 DB 저장

---

## 스택

| 항목 | 기술 |
|------|------|
| Backend | FastAPI + Uvicorn |
| DB | SQLite (SQLAlchemy) |
| 암호화 | cryptography (Fernet) |
| AI | OpenAI API · Anthropic API |
| 배포 | Docker · Kubernetes |
| Frontend | Jinja2 템플릿 (서버사이드 렌더링) |

---

## 빠른 시작

### 1. 설치

```bash
git clone https://github.com/junsungkim-lab/debait.git
cd debait

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열고 아래 값들을 채우세요:

| 변수 | 설명 | 생성 방법 |
|------|------|-----------|
| `WEBHOOK_SECRET` | Telegram webhook 검증용 시크릿 | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `TELEGRAM_BOT_TOKEN` | Telegram 봇 토큰 | [@BotFather](https://t.me/BotFather) 에서 발급 |
| `MASTER_KEY` | API 키 암호화용 Fernet 키 | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `BASE_URL` | 앱의 공개 URL | 예: `http://localhost:8000` |

### 3. 실행

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:8000` 접속

---

## Docker로 실행

```bash
docker compose up --build
```

---

## Kubernetes로 실행

`application.yaml.example`을 복사하고 실제 값으로 채운 뒤:

```bash
cp application.yaml.example application.yaml
# application.yaml 편집 후

docker build -t debait:latest .
kubectl apply -f application.yaml
```

`http://localhost:30090` 접속

---

## 사용 방법

### 웹에서 질문하기
1. `http://localhost:8000` 접속
2. Settings에서 OpenAI 또는 Anthropic API 키 등록
3. 질문 입력 → AI 토론 결과 확인

### Telegram 연결하기
1. Settings 페이지에서 **연결 코드** 확인
2. Telegram에서 봇에게 `/start` 전송
3. 연결 코드 전송 → 연결 완료
4. 이후 Telegram에서 질문하면 AI가 답변

### Telegram Webhook 설정 (외부 서버 배포 시)
```bash
python scripts/set_webhook.py
```

---

## 프로젝트 구조

```
debait/
├── app/
│   ├── main.py              # FastAPI 라우터
│   ├── models.py            # DB 모델 (SQLAlchemy)
│   ├── settings.py          # 환경변수 설정
│   ├── crypto.py            # API 키 암호화/복호화
│   ├── telegram.py          # Telegram 메시지 전송
│   ├── orchestrator/
│   │   ├── runner.py        # 오케스트레이터 엔진
│   │   ├── prompts.py       # AI 역할별 프롬프트
│   │   └── router.py        # SIMPLE/MULTI 라우팅
│   ├── providers/
│   │   ├── openai_provider.py
│   │   └── anthropic_provider.py
│   └── templates/           # HTML 템플릿
├── scripts/
│   ├── set_webhook.py
│   └── delete_webhook.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 모델 설정 예시

Settings 페이지에서 역할별 모델을 자유롭게 지정할 수 있습니다.

| 역할 | 저렴한 옵션 | 고품질 옵션 |
|------|------------|------------|
| Solver | `anthropic:claude-haiku-4-5-20251001` | `anthropic:claude-sonnet-4-6` |
| Critic | `anthropic:claude-haiku-4-5-20251001` | `anthropic:claude-sonnet-4-6` |
| Checker | `anthropic:claude-haiku-4-5-20251001` | `anthropic:claude-sonnet-4-6` |
| Synth | `anthropic:claude-haiku-4-5-20251001` | `anthropic:claude-sonnet-4-6` |

OpenAI: `openai:gpt-4o-mini` (저렴) / `openai:gpt-4o` (고품질)

---

## 주의사항

- 이 프로젝트는 **개인/학습용 1인 모드**입니다
- API 키는 서버에 암호화 저장되며 외부로 전송되지 않습니다
- 운영 환경에서는 SQLite → PostgreSQL, Secret Manager 도입 권장

---

## License

MIT
