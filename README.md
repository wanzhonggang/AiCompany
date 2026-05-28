# AI Employee Platform

面向企业的 AI 员工平台。系统把企业、部门、AI 员工、模型 Key、任务、会话、操作记录和员工记忆统一管理起来，老板或管理员可以像管理公司一样安排 AI 员工工作。

## 当前能力

- 企业注册与登录：支持企业入口、员工入口、管理员账号和员工账号。
- 多管理员：企业管理员可以创建其他管理员。
- 权限隔离：管理员管理本企业数据；员工账号只进入自己的工作台。
- AI 员工管理：新增员工、部门归属、模型选择、员工账号密码管理。
- 部门管理：维护部门职责、成员归属，AI 办公室按部门展示员工。
- 模型管理：企业独立配置 LLM API Key，未配置 Key 的模型不会给员工选择。
- 对话生成任务：用户直接在对话框里安排工作，由模型判断普通对话、立即任务、定时任务或多任务拆分。
- 例行工作：定时任务会显示在“例行工作”页，不需要用户单独新增例行工作。
- 账号与工具：当任务需要企业微信、飞书、微信、QQ、浏览器或 API 时，系统自动弹框让用户补充账号、登录或 API 信息，并保存到当前员工的账号工具中。
- 员工记忆/档案：职责、每日任务、账号说明、SOP、沟通规则、审批边界会注入每次执行 prompt。
- 任务记录：记录每个员工的任务状态、输出、错误、执行时间和会话关联。
- 执行进度：对话执行时展示分析、工具调用、工具结果、完成/失败状态；退出重进后会从历史工具记录恢复过程。
- 操作记录：记录最近 30 天的员工、任务、部门、模型等关键管理操作。
- 浏览器自动化：内置打开网页、点击、输入、截图等工具，用于网页/API 不好用时兜底。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | React 19 + TypeScript + Vite |
| 后端 | FastAPI + SQLAlchemy async |
| 数据库 | SQLite，本地文件位于 `backend/data/ai_employees.db` |
| LLM 调用 | OpenAI-compatible API，按企业保存 provider API Key |
| 实时输出 | SSE 流式对话 |
| 自动化工具 | 文件、网页搜索、浏览器、员工委派、邮件等工具 |

## 目录结构

```text
ai-employee-platform/
  backend/
    app/
      agent_runtime/        # Agent 运行时和工具
      routers/              # Auth、员工、任务、会话、部门、审计等 API
      auth.py               # 登录、Token、密码哈希
      config.py             # LLM 配置读取与保存
      database.py           # 数据库连接和轻量迁移
      main.py               # FastAPI 入口、模型管理、调度循环
      models.py             # SQLAlchemy 模型
      schemas.py            # Pydantic 请求/响应模型
      services.py           # 核心业务逻辑
      time_utils.py         # 北京时间工具
    data/
      ai_employees.db       # 本地 SQLite 数据库，已被 gitignore 忽略
    llm_config.json         # 模型供应商和模型清单
    requirements.txt
  frontend/
    public/
    src/
      api/client.ts
      pages/
      App.tsx
      index.css
    package.json
  README.md
```

## 本地启动

### 1. 安装依赖

```bash
cd backend
pip install -r requirements.txt

cd ../frontend
npm install
```

### 2. 启动后端

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

后端首次启动会初始化 SQLite 数据库，并创建默认企业和管理员账号：

```text
账号：admin
密码：admin123
```

### 3. 启动前端

```bash
cd frontend
npm run dev
```

默认访问：

```text
http://localhost:5173
```

## 基本使用流程

1. 企业入口登录或注册企业。
2. 管理员进入控制台，先到“模型管理”配置本企业可用模型的 API Key。
3. 创建部门和 AI 员工，为员工选择已配置 Key 的模型。
4. 在 AI 员工工作台直接对话安排工作。
5. 如果对话是普通聊天，员工直接回答。
6. 如果对话是工作安排，系统自动创建立即任务或定时任务。
7. 如果任务需要账号工具，系统会弹框让用户补充对应账号/API/登录说明。
8. 定时任务会显示在“例行工作”页，到点后自动生成任务记录并执行。

## 数据与缓存说明

已忽略的本地运行数据：

- `backend/data/*.db`
- `backend/data/browser_profiles/`
- `backend/browser_screenshots/`
- `backend/Desktop/`
- `backend/.env.local`
- `frontend/node_modules/`
- `frontend/dist/`
- `frontend/tsconfig.tsbuildinfo`
- `**/__pycache__/`

这些文件属于本地数据、构建产物或浏览器自动化缓存，不应提交到代码仓库。

## 常用 API

启动后端后访问 Swagger：

```text
http://localhost:8000/docs
```

常用接口：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/auth/register-enterprise` | 企业注册 |
| `POST` | `/api/auth/login` | 企业/员工登录 |
| `GET` | `/api/auth/me` | 当前登录用户 |
| `GET` | `/api/agents` | 员工列表 |
| `POST` | `/api/agents` | 创建 AI 员工 |
| `PATCH` | `/api/agents/{agent_id}` | 更新 AI 员工 |
| `POST` | `/api/chat/{agent_id}` | 员工 SSE 对话 |
| `GET` | `/api/chat/conversations/{agent_id}` | 会话列表 |
| `GET` | `/api/chat/messages/{conv_id}` | 会话消息 |
| `POST` | `/api/tasks/{agent_id}/plan` | 自然语言任务规划 |
| `GET` | `/api/tasks/agent/{agent_id}` | 员工任务记录 |
| `GET` | `/api/audit/logs` | 最近 30 天操作记录 |

## 开发约定

- 不要提交本地数据库、浏览器 profile、截图、构建产物和环境变量文件。
- 企业模型 Key 按企业隔离，新增企业默认无可用模型，需要管理员自行配置。
- 员工账号与工具只归属当前 AI 员工，不和其他员工共享。
- 对话是主要工作入口，任务和例行工作应尽量由对话自然生成。
- 涉及真实账号密码时，不建议保存明文密码；优先保存环境变量名、登录入口和人工登录说明。

## 验证命令

```bash
cd backend
python -m compileall app

cd ../frontend
npm run build
```
