# 🤖 Multi-Agent Workflow

> **여러 AI가 서로 토론하고, 가장 정제된 답 하나를 냅니다.**

AI 하나에게 묻는 대신, 구조화된 파이프라인을 실행합니다. **Solver**가 제안하고, **Critic**이 반박하고, **Checker**가 검증하고, **Synth**가 최종 정제된 답을 만듭니다. 로그인 없이 브라우저에서 즉시 사용 가능하며, 모든 단계와 모델은 **자유롭게 커스터마이즈** 가능합니다.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**🌐 언어:** [English](README.md) | 한국어 | [中文](README.zh.md)

---

![아키텍처](assets/architecture.png)

---

## ⚡ 30초 실행 (Python만 있으면 됩니다)

```bash
git clone https://github.com/junsungkim-lab/multi-agent-workflow.git
cd multi-agent-workflow
pip install -r requirements.txt
cp .env.example .env          # 키 입력 (아래 참고)
uvicorn app.main:app --port 8000
```

브라우저에서 `http://localhost:8000` 접속 → Settings에서 API 키 등록 → 질문 시작

> 대화 기록과 API 키는 `/data/app.db`에 로컬 저장되어 재시작해도 유지됩니다.

---

## 🎯 왜 Multi-Agent Workflow인가?

| | ChatGPT 단독 | AutoGen / CrewAI | **Multi-Agent Workflow** |
|--|--|--|--|
| 설치 | 즉시 | 복잡한 설정 | **명령어 3줄** |
| 토론 역할 | ❌ | 커스텀 에이전트 | **내장 + 자유 커스터마이즈** |
| 웹 UI | ❌ | ❌ | **✅ 기본 포함** |
| Telegram | ❌ | ❌ | **✅ 기본 포함** |
| 내 키 사용(BYOK) | ❌ | ❌ | **✅ 5개 provider** |
| 역할별 다른 모델 | ❌ | 부분 | **✅ 자유롭게 조합** |
| 파이프라인 커스터마이즈 | ❌ | 코드로만 | **✅ UI 에디터** |

---

## 💡 활용 예시

- **기술 결정** — "지금 단계에서 마이크로서비스 vs 모놀리식, 뭐가 나아?"
- **코드 리뷰** — 코드 붙여넣기 → Solver+Critic+Checker 관점 획득
- **리서치 요약** — 어떤 주제든 논거 비교
- **글쓰기** — 초안 → 비판 → 최종 완성본
- **리스크 분석** — 어떤 계획이든 Critic이 자동으로 약점을 찾아냄

---

## 🔧 지원 AI Provider

| Provider | 키 발급처 | 저렴한 모델 | 고품질 모델 |
|----------|----------|------------|------------|
| **OpenAI** | [platform.openai.com](https://platform.openai.com/api-keys) | `openai:gpt-4o-mini` | `openai:gpt-4o` |
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | `anthropic:claude-haiku-4-5-20251001` | `anthropic:claude-sonnet-4-6` |
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com/apikey) | `google:gemini-2.0-flash` | `google:gemini-2.5-pro-preview-05-06` |
| **Groq** | [console.groq.com](https://console.groq.com/keys) | `groq:llama-3.1-8b-instant` | `groq:llama-3.3-70b-versatile` |
| **Mistral** | [console.mistral.ai](https://console.mistral.ai/api-keys) | `mistral:mistral-small-latest` | `mistral:mistral-medium-latest` |

---

## 🏗️ 동작 원리

```
질문
  │
  ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 스테이지 1│──▶│ 스테이지 2│──▶│ 스테이지 N│──▶│  Synth   │
│          │   │          │   │          │   │          │
│ 해결안   │   │ 약점 지적│   │ 논리 검증│   │ 최종 답변│
└──────────┘   └──────────┘   └──────────┘   └──────────┘
   any LLM        any LLM        any LLM        any LLM
```

- 파이프라인 스테이지를 **UI에서 자유롭게** 추가/삭제/순서변경 (최대 6개)
- 각 스테이지마다 **이름**, **시스템 프롬프트**, **모델** 개별 설정 가능
- Synth는 항상 마지막에 고정 — 모든 스테이지 결과를 종합해 최종 답변 생성
- 단순 질문은 중간 스테이지를 건너뛰어 비용과 속도를 절약

---

## 🚀 전체 설정

### 1. 환경변수 설정

```bash
cp .env.example .env
```

| 변수 | 설명 |
|------|------|
| `MASTER_KEY` | API 키 암호화용 Fernet 키 |
| `WEBHOOK_SECRET` | Telegram webhook 검증 시크릿 |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather)에서 발급 |
| `BASE_URL` | 앱의 공개 URL (예: `http://localhost:8000`) |

키 생성:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. API 키 등록

`http://localhost:8000/settings` → API 키 붙여넣기
키는 **Fernet(AES-128)** 암호화 저장 — 평문 저장 없음

### 3. 파이프라인 커스터마이즈 (선택)

Settings → 토론 파이프라인 → 스테이지 추가/삭제/순서변경, 스테이지별 모델 지정

```
스테이지 1 (Solver)  → groq:llama-3.3-70b-versatile   # 빠름
스테이지 2 (Critic)  → anthropic:claude-haiku-4-5-20251001
스테이지 3 (Checker) → google:gemini-2.0-flash
Synth                → anthropic:claude-sonnet-4-6    # 고품질 최종 답변
```

---

## 🐳 Docker

```bash
docker compose up --build
```

## ☸️ Kubernetes

```bash
cp application.yaml.example application.yaml
# 시크릿 값 입력 후
docker build -t debait:latest .
kubectl apply -f application.yaml
# http://localhost:30090 접속
```

---

## 🔒 보안 & 프라이버시

- API 키는 **Fernet(AES-128-CBC)** 암호화 후 저장
- 키가 서버 밖으로 전송되지 않음
- 분석/텔레메트리 없음
- SQLite DB는 **로컬 저장** — 대화는 내 것

---

## 🗺️ 로드맵

- [ ] 실시간 스트리밍 응답
- [ ] 대화 Markdown/PDF 내보내기
- [ ] 멀티 라운드 토론 (반복 정제)
- [ ] RAG 지원 (문서 첨부)
- [ ] REST API

---

## 📄 라이선스

MIT

---

*도움이 됐다면 ⭐ 스타를 눌러주세요. 더 많은 사람들이 찾을 수 있게 됩니다.*
