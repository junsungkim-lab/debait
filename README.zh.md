# 🤖 Multi-Agent Workflow (Debait)

> **多个AI展开辩论，得出最优精炼答案。**

不同于只问一个AI，本项目运行结构化辩论管道：**Solver** 提出方案，**Critic** 指出漏洞，**Checker** 验证逻辑，**Synth** 生成最终精炼答案。无需登录，直接在浏览器中使用。所有阶段与模型均可**自由定制**。

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**🌐 语言:** [English](README.md) | [한국어](README.ko.md) | 中文

---

![架构图](assets/architecture.png)

---

## ⚡ 30秒快速启动（只需 Python）

```bash
git clone https://github.com/junsungkim-lab/multi-agent-workflow.git
cd multi-agent-workflow
pip install -r requirements.txt
cp .env.example .env          # 填写密钥（见下文）
uvicorn app.main:app --port 8000
```

浏览器访问 `http://localhost:8000` → Settings 中注册 API Key → 开始提问

> 本地 Python 运行默认使用 `./app.db`。
> Docker/Kubernetes 示例使用 `/data/app.db` 以便持久化存储。

---

## 🎯 为什么选择 Multi-Agent Workflow？

| | 单独 ChatGPT | AutoGen / CrewAI | **Multi-Agent Workflow** |
|--|--|--|--|
| 部署难度 | 即用 | 配置复杂 | **3条命令** |
| 辩论角色 | ❌ | 自定义 Agent | **内置 + 完全可定制** |
| Web UI | ❌ | ❌ | **✅ 开箱即用** |
| Telegram | ❌ | ❌ | **✅ 内置支持** |
| 自带密钥(BYOK) | ❌ | ❌ | **✅ 5个Provider** |
| 按角色混用模型 | ❌ | 部分 | **✅ 自由组合** |
| 管道阶段定制 | ❌ | 仅代码 | **✅ UI编辑器** |

---

## 💡 使用场景

- **技术选型** — "当前阶段应该用微服务还是单体架构？"
- **代码审查** — 粘贴代码，获取 Solver+Critic+Checker 多角度分析
- **研究综合** — 任意话题的论据对比
- **写作辅助** — 草稿 → 批评 → 最终完善版本
- **风险分析** — 任何方案都会被 Critic 自动找出弱点

---

## 🔧 支持的 AI Provider

| Provider | 获取密钥 | 低价模型 | 高质量模型 |
|----------|---------|---------|---------|
| **OpenAI** | [platform.openai.com](https://platform.openai.com/api-keys) | `openai:gpt-4o-mini` | `openai:gpt-4o` |
| **Anthropic** | [console.anthropic.com](https://console.anthropic.com/settings/keys) | `anthropic:claude-haiku-4-5-20251001` | `anthropic:claude-sonnet-4-6` |
| **Google Gemini** | [aistudio.google.com](https://aistudio.google.com/apikey) | `google:gemini-2.0-flash` | `google:gemini-2.5-pro-preview-05-06` |
| **Groq** | [console.groq.com](https://console.groq.com/keys) | `groq:llama-3.1-8b-instant` | `groq:llama-3.3-70b-versatile` |
| **Mistral** | [console.mistral.ai](https://console.mistral.ai/api-keys) | `mistral:mistral-small-latest` | `mistral:mistral-medium-latest` |

---

## 🏗️ 工作原理

```
您的问题
   │
   ▼
┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│  阶段 1  │──▶│  阶段 2  │──▶│  阶段 N  │──▶│  Synth   │
│          │   │          │   │          │   │          │
│ 提出方案 │   │ 指出漏洞 │   │ 验证逻辑 │   │ 最终答案 │
└──────────┘   └──────────┘   └──────────┘   └──────────┘
  any LLM        any LLM        any LLM        any LLM
```

- 通过 Settings UI **自由定制**管道阶段（添加/删除/排序，最多6个）
- 每个阶段可单独设置**名称**、**系统提示词**和**模型**
- Synth 始终最后执行，汇总所有阶段输出生成最终答案
- 简单问题跳过中间阶段，节省成本与时间

---

## 🚀 完整配置

### 1. 环境变量配置

```bash
cp .env.example .env
```

| 变量 | 说明 |
|------|------|
| `MASTER_KEY` | 用于加密存储 API Key 的 Fernet 密钥 |
| `WEBHOOK_SECRET` | Web+Telegram 模式需要（Webhook 验证密钥） |
| `TELEGRAM_BOT_TOKEN` | Web+Telegram 模式需要（从 [@BotFather](https://t.me/BotFather) 获取） |
| `BASE_URL` | 应用的公开 URL（如 `http://localhost:8000`）|
| `DB_URL` | 可选，默认 `sqlite:///./app.db` |

生成密钥：
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 2. 注册 API Key

访问 `http://localhost:8000/settings` → 粘贴 API Key
Key 使用 **Fernet(AES-128)** 加密存储，不保存明文

### 3. 自定义管道（可选）

Settings → Debate Pipeline → 添加/删除/排序阶段，按阶段分配模型

```
阶段1 (Solver)  → groq:llama-3.3-70b-versatile      # 速度快
阶段2 (Critic)  → anthropic:claude-haiku-4-5-20251001
阶段3 (Checker) → google:gemini-2.0-flash
Synth           → anthropic:claude-sonnet-4-6        # 高质量最终答案
```

---

## 🐳 Docker

```bash
docker compose up --build
```

使用 `DB_URL=sqlite:////data/app.db`，并将主机 `./data` 挂载到容器 `/data`。

## ☸️ Kubernetes

```bash
cp application.yaml.example application.yaml
# 填写密钥后
docker build -t debait:latest .
kubectl apply -f application.yaml
# 访问 http://localhost:30090
```

`application.yaml.example` 已包含 `DB_URL=sqlite:////data/app.db` 和 `/data` 的 PVC 挂载配置。

---

## 🔒 安全与隐私

- API Key 使用 **Fernet(AES-128-CBC)** 加密后存储
- 密钥不会离开您的服务器
- 无分析，无遥测
- SQLite 数据库**本地存储**——对话属于您自己

---

## 🗺️ 路线图

- [ ] 实时流式响应
- [ ] 导出对话为 Markdown/PDF
- [ ] 多轮辩论（迭代优化）
- [ ] RAG 支持（附加文档）
- [ ] REST API

---

## 📄 许可证

MIT

---

*如果对您有帮助，请点 ⭐ 支持项目，让更多人发现它。*
