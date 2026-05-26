# AI Employee Platform

AI 数字员工管理平台 — 创建、管理和调度 AI 员工执行真实工作任务。

## 架构

```
┌──────────────────────────────────────────────────────────┐
│  前端 (React 19 + Vite + TypeScript)                      │
│  控制台 / AI员工管理 / SSE流式对话                         │
└────────────────────────┬─────────────────────────────────┘
                         │ REST + SSE
┌────────────────────────┴─────────────────────────────────┐
│  后端 (Python 3.14 + FastAPI)                             │
│  Agent CRUD / 对话 / 任务 / 统计                          │
│                                                           │
│  Agent 运行时 (自建 ReAct 循环)                            │
│  ┌─────────────────────────────────────────────────┐     │
│  │ 1. 组装上下文 → 2. 调用 Claude API              │     │
│  │ 3. 解析响应 → 有工具调用? → 执行工具 → 回到 2   │     │
│  │ 4. 返回最终结果                                  │     │
│  └─────────────────────────────────────────────────┘     │
│                                                           │
│  工具平台: 文件读写 / 目录操作 / 网页搜索 / 邮件发送       │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│  存储: SQLite (async)                                     │
└──────────────────────────────────────────────────────────┘
```

## 项目结构

```
ai-employee-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口 + 种子数据
│   │   ├── config.py            # 配置 (API Key, 路径等)
│   │   ├── database.py          # SQLite async 连接
│   │   ├── models.py            # 数据模型 (Agent, Task, Conversation, Message)
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── services.py          # 业务逻辑层
│   │   ├── routers/
│   │   │   ├── agents.py        # Agent CRUD + 统计 API
│   │   │   ├── chat.py          # SSE 流式对话 API
│   │   │   ├── tools.py         # 工具列表 API
│   │   │   └── tasks.py         # 任务管理 API
│   │   └── agent_runtime/
│   │       ├── core.py          # ReAct 循环引擎 (AgentRuntime)
│   │       └── tools/
│   │           ├── base.py      # BaseTool 抽象类
│   │           ├── file_tools.py # 文件读写、列目录
│   │           ├── web_tools.py  # 网页搜索、抓取
│   │           └── email_tools.py# SMTP 邮件发送
│   ├── .env                     # 环境变量 (API Key)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 路由 + 布局
│   │   ├── main.tsx             # 入口
│   │   ├── index.css            # 暗色主题全局样式
│   │   ├── api/
│   │   │   └── client.ts        # API 封装 (REST + SSE)
│   │   └── pages/
│   │       ├── Dashboard.tsx    # 控制台 (概览 + 统计)
│   │       ├── Agents.tsx       # AI 员工管理 (CRUD + 搜索)
│   │       └── AgentChat.tsx    # SSE 流式对话界面
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── .claude/                     # Claude Code 配置
└── README.md
```

## 快速开始

### 前提条件

- Python 3.14+
- Node.js 20+
- [Anthropic API Key](https://console.anthropic.com/) (Claude API)

### 1. 配置 API Key

```bash
cd backend
cp .env .env.example   # 如有需要
# 编辑 .env，设置 ANTHROPIC_API_KEY
```

`.env` 内容：
```ini
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
SECRET_KEY=change-me-in-production
```

可选 SMTP 配置（用于邮件工具）：
```ini
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-email@gmail.com
```

### 2. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

### 3. 启动服务

**终端 1 — 后端：**
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**终端 2 — 前端：**
```bash
cd frontend
npm run dev
```

### 4. 打开浏览器

访问 **http://localhost:5173**

首次启动会自动创建 4 个示例 AI 员工（Alpha 分析师、Beta 工程师、Gamma 秘书、Delta 研究员），每个员工默认启用全部 6 个工具。

## API 文档

启动后端后访问 **http://localhost:8000/docs** 查看 Swagger UI。

### 核心端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/agents/stats` | Agent 统计 (总数/状态分布) |
| GET | `/api/agents` | 列出所有 Agent |
| POST | `/api/agents` | 创建 Agent |
| GET | `/api/agents/{id}` | 获取 Agent 详情 |
| PATCH | `/api/agents/{id}` | 更新 Agent |
| DELETE | `/api/agents/{id}` | 删除 Agent |
| POST | `/api/chat/{agent_id}` | SSE 流式对话 |
| GET | `/api/chat/conversations/{agent_id}` | 对话历史列表 |
| GET | `/api/tools` | 可用工具列表 |
| POST | `/api/tasks/{agent_id}` | 创建任务 |
| GET | `/api/tasks/agent/{agent_id}` | 任务列表 |

## 内置工具

| 工具 | 名称 | 需人工审批 | 说明 |
|------|------|------------|------|
| `read_file` | 读文件 | 否 | 读取工作区内的文件 |
| `write_file` | 写文件 | 是 | 写入文件到工作区 |
| `list_directory` | 列目录 | 否 | 列出目录内容 |
| `web_search` | 搜索网页 | 否 | DuckDuckGo 搜索 |
| `web_fetch` | 抓取网页 | 否 | 获取网页文本内容 |
| `send_email` | 发送邮件 | 否 | 通过 SMTP 发送邮件 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端框架 | React 19 + TypeScript + Vite 6 |
| UI 样式 | 自定义暗色主题 CSS |
| 后端框架 | Python 3.14 + FastAPI |
| Agent 运行时 | 自建 ReAct 循环 + Anthropic SDK |
| 数据库 | SQLite (async/aiosqlite) + SQLAlchemy 2.0 |
| LLM | Claude Opus 4.7 / Sonnet 4.6 |

## 架构决策

### 为什么自建 Agent 运行时而不是用 LangChain？

1. **可控性**: ~200 行的 ReAct 循环，每一步都是透明的
2. **调试性**: 每一个 LLM 调用、工具执行都是可追踪的
3. **可观测性**: 自定义事件流，便于前端实时展示
4. **少抽象**: 不使用 LangChain 的 Agent Executor，直接用 Anthropic SDK

### 为什么用 SSE 而不是 WebSocket？

Agent 对话是单向流（请求 → 流式响应），不需要双向通信。SSE 更简单、更可靠、浏览器原生支持自动重连。

### 下一步

按方案路线图逐步添加：
- Phase 2: 微信集成 (WeChatFerry) + 多 Agent 协作
- Phase 3: 多租户 + RBAC + 计费
- Phase 4: K8s 部署 + 插件市场
