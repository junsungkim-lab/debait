# 🤖 Debait — 多AI辩论引擎

> **多个AI展开辩论，得出最优答案。**

不同于只问一个AI，Debait 运行结构化辩论：**Solver** 提出方案，**Critic** 指出漏洞，**Checker** 验证逻辑，**Synth** 生成最终精炼答案。无需登录，直接在浏览器中使用。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**🌐 语言:** [English](README.md) | [한국어](README.ko.md) | 中文

---

![架构图](assets/architecture.png)

---

## ⚡ 30秒快速启动（只需 Python）

```bash
git clone https://github.com/junsungkim-lab/debait.git
cd debait
pip install -r requirements.txt
cp .env.example .env          # 填写密钥（见下文）
uvicorn app.main:app --port 8000
```

浏览器访问 `http://localhost:8000` → Settings 中注册 API Key → 开始提问

> 对话记录和 API Key 保存在本地 `app.db` 文件中，重启后数据不丢失。

---

## 🎯 为什么选择 Debait？

| | 单独 ChatGPT | AutoGen / CrewAI | **Debait** |
|--|--|--|--|
| 部署难度 | 即用 | 配置复杂 | **3条命令** |
| 辩论角色 | ❌ | 自定义 Agent | **内置（Solver/Critic/Checker/Synth）** |
| Web UI | ❌ | ❌ | **✅ 开箱即用** |
| Telegram | ❌ | ❌ | **✅ 内置支持** |
| 自带密钥(BYOK) | ❌ | ❌ | **✅ 5个Provider** |
| 按角色混用模型 | ❌ | 部分 | **✅ 自由组合** |

---

## 💡 使用场景

- **技术选型** — "当前阶段应该用微服务还是单体架构？"
- **代码审查** — 粘贴代码，获取 Solver+Critic+Checker 多角度分析
- **研究综合** — 任意话题的论据对比
- **写作辅助** — 草稿 → 批评 → 最终完善版本
- **风险分析** — 任何方案都会被 Critic 自动找出弱点

---

## 🔧 支持的 AI Provider

| Provider | 获取密钥 | 推荐模型 |
|----------|---------|---------|
| **OpenAI** | [platform.openai.com](https://platform.openai.com/api-keys) | `openai:gpt-4o-mini` |
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | `anthropic:claude-haiku-4-5-20251001` |
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com/apikey) | `google:gemini-2.0-flash` |
| **Groq** | [console.groq.com](https://console.groq.com/keys) | `groq:llama-3.3-70b-versatile` |
| **Mistral** | [console.mistral.ai](https://console.mistral.ai/api-keys) | `mistral:mistral-small-latest` |

---

## 🚀 完整配置

### 1. 环境变量配置

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `MASTER_KEY` | 用于加密存储 API Key 的 Fernet 密钥 |
| `WEBHOOK_SECRET` | Telegram Webhook 验证密钥 |
| `TELEGRAM_BOT_TOKEN` | 从 [@BotFather](https://t.me/BotFather) 获取 |
| `BASE_URL` | 应用的公开 URL（如 `http://localhost:8000`）|

生成密钥：
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. 注册 API Key

访问 `http://localhost:8000/settings` → 粘贴 API Key
Key 使用 **Fernet(AES-128)** 加密存储，不保存明文

### 3. 按角色配置模型（可选）

```
Solver  → groq:llama-3.3-70b-versatile      # 速度快
Critic  → anthropic:claude-haiku-4-5-20251001
Checker → google:gemini-2.0-flash
Synth   → anthropic:claude-sonnet-4-6        # 高质量最终答案
```

---

## 🐳 Docker

```bash
docker compose up --build
```

## ☸️ Kubernetes

```bash
cp application.yaml.example application.yaml
# 填写密钥后
docker build -t debait:latest .
kubectl apply -f application.yaml
# 访问 http://localhost:30090
```

---

## 🔒 安全与隐私

- API Key 使用 **Fernet(AES-128-CBC)** 加密后存储
- 密钥不会离开您的服务器
- 无分析，无遥测
- SQLite 数据库**本地存储**——对话属于您自己

---

## 🗺️ 路线图

- [ ] 实时流式响应
- [ ] 通过 UI 自定义角色提示词
- [ ] 导出对话为 Markdown/PDF
- [ ] 多轮辩论（迭代优化）
- [ ] RAG 支持（附加文档）

---

## 📄 许可证

MIT

---

*如果 Debait 对您有帮助，请点 ⭐ 支持项目，让更多人发现它。*
