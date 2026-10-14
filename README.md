# ERP 智能采购助手 — Harness Engineering 架构

> 基于 DeepAgent + LangGraph + MCP 协议的摩托车零部件采购智能助手，严格遵循 **Harness Engineering** 架构思想（Planning → Executing → Review → Result）。

---

## 项目简介

本项目是一个面向摩托车零部件采购管理场景的 **AI Agent 系统**。通过大语言模型（通义千问 qwen-plus）驱动的智能体，与已部署的 Java ERP 后端进行交互，实现：

- 供应商智能分析（信用评级、供货能力对比）
- 采购订单全生命周期管理（创建/修改/审批）
- 库存预警与出入库管理
- 零部件搜索与供应商关联查询
- 数据可视化图表生成（26 种图表类型）
- 结构化文档输出（Markdown/HTML/CSV/JSON）
- 人工审批流程（HITL — Human-in-the-Loop）

---

## 技术栈

| 层级 | 技术                                    | 说明                      |
|------|---------------------------------------|-------------------------|
| **LLM** | 通义千问 qwen-plus                        | 阿里云 DashScope API       |
| **Agent 框架** | DeepAgent + LangGraph                 | 状态图引擎，支持中断/恢复/子Agent    |
| **MCP 协议** | FastMCP + SSE                         | Agent ↔ ERP 的工具桥接层      |
| **Web 框架** | FastAPI + Uvicorn                     | SSE 流式响应                |
| **前端** | Next.js 16 + React 19 + TailwindCSS 4 | 流式对话 UI + 中断交互          |
| **数据库** | MongoDB (Motor/Pymongo)               | 会话/消息/Store 持久化         |
| **沙箱** | OpenSandbox                           | 阿里沙箱隔离代码执行环境            |
| **图表** | Matplotlib + Pandas                   | 26 种图表生成                |
| **语言** | Python 3.11+ / TypeScript             | 后端 Python，前端 TypeScript |

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js :3000)                       │
│              SSE 流式对话 + HITL 中断交互 + 历史管理              │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼────────────────────────────────────┐
│              Backend API (FastAPI :8000)                          │
│   chat.py (SSE流) + history.py (会话CRUD) + agent_loader.py      │
│   MongoDBStore + MongoDBSaver (生产级持久化)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│              Agent Core (DeepAgent)                               │
│  ┌──────────┐ ┌───────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │ LLM      │ │ Composite     │ │ 9 中间件     │ │ 2 子Agent  │ │
│  │ qwen-plus│ │ Backend       │ │ (7自定义     │ │ analyst    │ │
│  │          │ │ (Docker+Store)│ │  +2框架内置) │ │ order      │ │
│  └──────────┘ └───────────────┘ └─────────────┘ └────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Tools: 12 MCP + 9 Custom = 21 个工具                         ││
│  │ chart(26种) + websearch  + skillmanage         ││
│  │ + queryorderinfo + download     ││
│  └─────────────────────────────────────────────────────────────┘│
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP (SSE)
┌────────────────────────────▼────────────────────────────────────┐
│              MCP Server (FastMCP :9000)                           │
│   supplier(5) + part(3) + order(3) + inventory(1) = 10 tools │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP REST
┌────────────────────────────▼────────────────────────────────────┐
│              Java ERP 后端 (:8081)                                │
│              http://47.92.108.163:8081                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心功能

### 1. Harness 工作流（Planning → Executing → Review → Result）
Agent 严格遵循四阶段工作流：
- **Planning**：分析用户意图，生成任务规划（前端展示 TodoList）
- **Executing**：调用 MCP 工具 / 沙箱执行代码 / 委派子Agent
- **Review**：审查执行结果，验证数据完整性
- **Result**：结构化输出最终结果

### 2. opensandbox 安全沙箱（9 层防护）
```
1. --read-only          文件系统可以配置只读，文件通过OpenSandbox的文件代理上传 / 下载沙箱内是独立临时文件系统，沙箱销毁后所有文件自动清除
2. --tmpfs /tmp         临时目录内存挂载（限制大小）
3. --memory="512m"      内存上限
4. --cpus="1.0"         CPU 上限
5. --network bridge     网络隔离/受限。默认可以配置`default_action: deny`，**默认禁止沙箱访问任何外网**
6. --cap-drop ALL       移除所有 Linux Capability
7. --security-opt       seccomp 系统调用白名单
8. --TTL                自动过期，置沙箱自动销毁，避免僵尸沙箱堆积占用资源，访问时自动续期保活
9. --white-list         白名单机制：只允许 skill 需要访问的域名，例如仅允许 pypi 下载包，禁止访问内网数据库、内部服务、公网任意地址，**防止代码把内部 memory、业务数据外发**
```
支持可扩展多语言运行时：Python / Go / Node.js，- 还支持 Playwright 浏览器自动化，适合多种 skill（数据分析、文件处理、网页抓取）open-sandb...

### 3. 沙箱五态生命周期管理
```
Sandbox Pool(沙箱池) → 认领(CLAIMED) → MongoDB缓存(CACHED)
     ↑                              │
     │ 补充预热                       │ 故障/超时
     │                              ↓
  新建(CREATE) ←────────────── 销毁(DESTROY)--手动销毁+自动ttl回收
  
  OpenSandbox 内置 SandboxPool：预先创建一批就绪沙箱，请求来的时候直接 acquire，用完归还 / 销毁，消除创建镜像、启动 pod 的冷启动延迟，适合大量并发 Agent skill 请求。
  OpenSandbox 生命周期由独立控制器管理，沙箱有完整状态机，支持创建、运行、暂停、快照、续期、销毁；**两种模式：一次性用完即销毁（安全优先）、长存活 + TTL 自动回收（性能优先）；Agent 场景一个用户 thread 独占一个沙箱，绝对不共享。
  
```

### 4. HITL 人工审批
- 订单创建/更新触发 `interrupt_on` 中断
- 前端展示审批卡片，用户批准后恢复执行
- 缺少字段时触发信息补充中断

### 5. 子Agent 委派
- **purchase_analyst**：采购分析师（数据分析 + 图表生成）
- **purchase_order**：订单专家（订单 CRUD + 审批流程）

### 6. 8 层中间件栈
| # | 中间件 | 职责 |
|---|--------|------|
| 1 | ContextInjectionMiddleware | 用户上下文注入（工厂模式隔离） |
| 2 | SyncSkillsMiddleware | 技能文件夹级增量同步 |
| 3 | RestoreSkillsMiddleware | 用户自定义技能恢复 |
| 4 | ToolsSummarizationMiddleware | 工具调用摘要监控 |
| 5 | UpdateMemoryMiddleware | 用户偏好自动提取 |
| 6 | SandboxCircuitBreakerMiddleware | 沙箱熔断器（三态模型） |
| 7 | ModelCallLimitMiddleware | 模型调用次数限制 |
| 8 | ToolCallLimitMiddleware | 工具调用次数限制 |

### 7. 21 个工具
- **12 个 MCP 工具**：供应商(5) + 零部件(3) + 订单(3) + 库存(1)
- **9 个自定义工具**：chart_generator, web_search, web_fetch, install_skill, request_order_info, download_sandbox_file, list_sandbox_files, generate_document, generate_table_report

---

## 项目结构

```
Erp_Purchase_Agent/
├─frontend
│  │  index.html
│  │  package-lock.json
│  │  package.json
│  │  vite.config.js
│  │  
│  └─src
│      │  App.vue
│      │  main.js
│      │  
│      ├─api
│      │      chat.js
│      │      history.js
│      │      
│      ├─components
│      │      ChatArea.vue
│      │      InputArea.vue
│      │      InterruptBanner.vue
│      │      MarkdownRenderer.vue
│      │      MessageItem.vue
│      │      Sidebar.vue
│      │      ToolCallPanel.vue
│      │      
│      └─styles
│              main.css
│
├─agent
│  │  agentconfig.py                    # agent 配置信息
│  │  agentcreator.py                   # agent 生成器
│  │  
│  ├─manage
│  │      sandboxbackendmanage.py       # 沙箱后端管理（包括沙箱环境初始化、初始化文件到沙箱环境、沙箱环境执行命令、在沙箱环境上传\下载文件）
│  │      
│  ├─middlewares
│  │      middlewarefactory.py          # 中间件创建工厂（包含上下文注入（工厂模式隔离）、技能同步（文件夹级增量+沙箱传输）、技能恢复（增量+空值保护）、偏好提取、会话摘要等以及绑定子agent相关的中间件创建）
│  │      
│  ├─sandbox
│  │      custom_opensandbox.py
│  │      sandboxcreator.py             # 沙箱生成器
│  │      sandbox_holder.py
│  │      sandbox_manager.py
│  │      sandbox_proxy.py
│  │      sandbox_setup.py
│  │      seccomp.json
│  │      
│  └─tools
│          createdownloadtool.py        # 沙箱文件下载
│          createvisualtool.py          # 生成表格视图工具
│          queryorderinfotool.py        # 查询订单信息工具
│          skillmanagetool.py           # 将 /skills下已验证的技能分配给指定 Agent（主 Agent 或子 Agent）。支持 StoreBackend 持久化 + 压缩包清理。
│          websearchtool.py             # 基于智谱 AI 的搜狗 Web Search API，供主 Agent 和所有子 Agent 使用。
│          
├─api
│      app.py                           # FastAPI 定义
│      chat.py                          # SSE 流式对话（包括human-in-the-loop接口）
│      check_health.py                  # 服务是否启动成功健康检查接口
│      history.py                       # 历史会话 CRUD
│      
├─bean
│      parambean.py                     # 入参和出参实体
│      
├─config
│  │  config.py                         # 全局配置
│  │  
│  └─__pycache__
│          config.cpython-313.pyc
│          
├─contextmanager
│      webcontextmanager.py             # FastAPI 里最常用：lifespan 生命周期。全局异步上下文管理器
│      
│              
├─llm
│      my_llm.py                        # 大模型
│      
├─mcpclient
│      mcpclient.py                     # MCP工具加载（重试/缓存/优雅降级）
│      
├─mcpserver
│  │  httpbase.py                       # HTTP客户端
│  │  server.py                         # FastMCP入口
│  │  serverconfig.py                   # MCP服务配置信息
│  │  
│  └─interface
│          inventorytool.py             # 库存预警
│          ordertool.py                 # 订单工具
│          parttool.py                  # 零部件工具
│          suppliertool.py              # 供应商工具
│          
├─service
│      agentchatservice.py              # 智能体具体业务层
│      mongodbservice.py                # 持久化具体业务层
│      
├─skills
│  ├─manage                             # 技能管理
│  │  │─scripts
│  │  │     download_script.py          # 技能下载单独验证脚本
│  │  │ SKILL.md
│  │      
│  └─purchase
│      │  chart_params.md
│      │  
│      ├─purchase-analyst               # 采购技能集（8个子skill）
│      │      SKILL.md
│      │      
│      ├─supplier-price-urls            # 根据供应商报价地址获取报价数据
│      │  │  SKILL.md
│      │  │  
│      │  └─data
│      │          url_mapping.yaml
│      │          
│      └─web-crawler                    # 网络爬虫技能
│              meta.json
│              page_crawler.py
│              SKILL.md
│              
└─subagents                             # 子agent层
    │  subagentcreator.py               # 子agent生成器
    │  
    └─configs                           # 子agent技能配置信息
            purchase_analyst.yaml
            purchase_order.yaml
```

---

## 快速启动

### 环境要求

- Python 3.11+
- Node.js 18+
- MongoDB 6.0+
- Docker Desktop（已启动）
- 通义千问 API Key（DashScope）

### 1. 克隆项目 & 安装依赖

```bash
# 克隆项目
git clone <repo-url>
cd Erp_Purchase_Agent

# Python 依赖
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
cd ..
```

### 2. 配置环境变量

编辑项目根目录 `.env` 文件：

```bash
# 通义千问 API Key（阿里云 DashScope）
DASHSCOPE_API_KEY=sk-your-api-key

# MongoDB 连接
MGDB_URI=mongodb://localhost:27017

# Java ERP 后端地址
ERP-API.URL=http://localhost:8080/api

# MCP Server 地址（本地）
MCP_SERVER_URL=http://localhost:9000

# 沙箱 Docker 镜像
SANDBOX_IMAGE=python:3.11-slim
```

### 3. 启动 MongoDB

```bash
# 确保 MongoDB 正在运行
mongod --dbpath /path/to/data

# 或使用 Docker
docker run -d --name mongodb -p 27017:27017 mongo:6.0
```

### 4. 启动 沙箱容器

```bash
# Generate a starter config
uvx opensandbox-server init-config ~/.sandbox.toml --example docker

# Start the server
uvx opensandbox-server
# or specify a config path
opensandbox-server --config /path/to/sandbox.toml

Docker 上的 gVisor
[runtime]
type = "docker"
execd_image = "opensandbox/execd:latest"

[secure_runtime]
type = "gvisor"
docker_runtime = "runsc"
k8s_runtime_class = "gvisor"
```

### 5. 启动 MCP Server（端口 9000）

```bash
python -m mcpserver.server
```

看到以下输出表示成功：
```
🚀 Starting MCP Server on 0.0.0.0:9000 (SSE transport)
Uvicorn running on http://0.0.0.0:9000
```

### 6. 启动后端 API（端口 8000）

```bash
python -m api.app 
```

看到以下输出表示成功：
```
AgentLoader initialized
Starting ERP Agent Web Server...
Uvicorn running on http://0.0.0.0:8000
```

### 7. 启动前端（端口 3000）

```bash
cd frontend
npm run dev
```

### 8. 访问应用

浏览器打开 http://localhost:3000 即可使用。

---

## 启动顺序总结

```
MongoDB → opensandbox沙箱 → MCP Server(:9000) → Backend API(:8000) → Frontend(:3000)
```

> 注意：MCP Server 必须在 Backend API 之前启动，因为 Agent 初始化时会连接 MCP Server 加载 23 个 ERP 工具。

---

## 项目亮点

### 1. 真正的 Harness Engineering 架构
不是简单的 ChatBot，而是严格遵循 **Planning → Executing → Review → Result** 四阶段工作流。前端实时展示每个阶段的状态变化（Phase Bar + TodoList），用户可清晰看到 Agent 的思考和执行过程。

### 2. 生产级 opensandbox 安全沙箱
控制平面（生命周期 API，FastAPI） + 数据平面（沙箱 Pod/MicroVM 执行环境）分离；一个 Agent Thread 独占一个沙箱，禁止多租户共享沙箱，专门用来运行 LLM 生成的不可信 Python/Shell 代码、数据分析、文件处理 Skill。支持多语言运行时扩展（Python/Go/Node.js），项目文件完整同步到沙箱实现真正隔离测试。
生产底线：runc 仅开发，生产推荐 gVisor；高风险外部用户使用 Firecracker MicroVM

### 3. 五态沙箱生命周期
预热池 → 认领 → MongoDB 缓存 → 新建 → 销毁。服务重启不丢失用户绑定关系，预热池保证 < 100ms 分配速度，健康检查 + 自动重建故障容器。

### 4. 完整的 HITL 审批流程
订单创建/更新需人工审批，缺少字段时触发信息补充中断。基于 LangGraph 的 interrupt/resume 机制，前端展示审批卡片和信息补充表单。

### 5. 9 层中间件栈
沙箱健康检查、用户上下文注入（工厂模式防串扰）、技能增量同步、用户技能恢复、工具摘要监控、偏好自动提取、熔断器保护、调用限制。每个中间件都有明确的职责边界。

### 6. MCP 协议解耦
Agent 不直接调用 ERP API，而是通过 MCP Server 提供的 21 个标准化工具交互。MCP 层可独立部署、独立扩展，Agent 侧无需关心 ERP 接口细节。

### 7. MongoDB 全链路持久化
- **MongoDBSaver**：LangGraph Checkpointer（会话状态持久化）
- **MongoDBStore**：LangGraph Store（跨会话用户偏好/技能存储）
- **display_messages**：前端展示消息持久化
- **conversations**：会话列表管理

### 8. 子Agent 委派 + YAML 声明式配置
采购分析师和订单专家两个子Agent，通过 YAML 文件声明式配置（工具集、系统提示词、委派规则），主Agent 根据任务类型自动委派。

### 9. SSE 流式协议
完整的 SSE 事件协议：`thinking` → `token` → `tool_start` → `tool_result` → `phase` → `todo_update` → `interrupt` → `done`。前端逐 token 渲染，实时展示工具调用和阶段变化。

### 10. 技能系统（Skills）
文件夹级技能管理（SKILL.md + 脚本 + 依赖），支持安装/同步/恢复。SyncSkillsMiddleware 实现增量同步（SHA256 哈希比对），保留完整目录结构。

---

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/stream` | SSE 流式对话 |
| POST | `/api/chat/resume` | 中断恢复 |
| GET | `/api/chat//state/{thread_id}` | 获取中断状态 |
| GET | `/api/chat/{thread_id}/history` | 获取消息历史 |
| GET | `/api/history` | 获取会话列表 |
| DELETE | `/api/history/{thread_id}` | 删除会话 |
| GET | `/api/history/{thread_id}/messages` | 获取会话消息历史 |
| GET | `/api/health` | 健康检查 |

---

## 开发说明

- 后端代码详细解析见 [PROJECT_DOC.MD](./PROJECT_DOC.md)
- 修改 Agent 行为：编辑 `agent/agentconfig.py`（系统提示词）
- 添加新工具：在 `agent/tools/` 创建工具文件，在 `agentcreator.py` 注册
- 添加新中间件：在 `agent/middlewares/middlewarefactory.py` 创建，在 `agentcreator.py` 中间件栈中添加
- 修改子Agent：编辑 `subagents/configs/*.yaml`
