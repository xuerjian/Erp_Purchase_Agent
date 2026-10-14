Python 后端代码完全解析 — 从零理解智能采购助手

> 本文档按照逻辑阅读顺序，逐文件解析整个 Python 后端代码。每个章节包含文件路径、核心代码（含中文注释）、模块间关系和设计决策说明。按照顺序阅读，即可从零理解项目是如何运作的。

---

## 第1章 — 项目概览与架构

### 1.1 项目定位

本项目是一个基于 **Harness Engineering 架构**的 **ERP 智能采购助手**，专门服务于摩托车零部件采购管理业务。核心思想是：通过 AI Agent（基于 `deepagents` 框架）与已部署的 Java ERP 后端交互，实现供应商分析、采购订单管理（含人工审批）、图表生成、库存预警等智能化功能。

### 1.2 技术栈速览

| 技术 | 用途 | 版本/说明 |
|------|------|-----------|
| **deepagents** | Agent 框架 | 基于 LangGraph 的高层封装 |
| **LangGraph** | 状态图引擎 | Agent 执行引擎，支持中断/恢复 |
| **LangChain** | LLM 工具链 | ChatOpenAI（通义千问兼容接口） |
| **FastAPI** | Web 框架 | SSE 流式响应 |
| **FastMCP** | MCP 协议 | Agent ↔ ERP 的工具桥接 |
| **Docker SDK** | 沙箱 | 隔离代码执行环境 |
| **MongoDB (Motor)** | 数据库 | 会话/消息持久化 |
| **通义千问** | LLM | qwen-plus 模型 |

### 1.3 完整目录树（Python 后端）
```
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

### 1.4 四层架构图

```
┌─────────────────────────────────────────────────────────────┐
│                   Frontend (Next.js :3000)                   │
│                 SSE 流式对话 + 中断交互                       │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP/SSE
┌───────────────────────────▼─────────────────────────────────┐
│             api (FastAPI :8000)                         │
│  app.py → chat.py (SSE流) / history.py (会话管理)       │
│  agentcreator.py (Agent单例) / agentconfig.py (MongoDB)       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│             agent (DeepAgent 核心)                            │
│  agentcreator.py → get_deep_agent()                         │
│  ┌──────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────┐ │
│  │ LLM      │ │ Backend   │ │ 7中间件    │ │ 子Agent(YAML)│ │
│  │ qwen-plus│ │ opensandbox │ │ 健康/注入/ │ │ analyst/order│ │
│  │          │ │ Composite │ │ 同步/恢复/ │ │ 上下文协议    │ │
│  │          │ │ Backend   │ │ 摘要/偏好/ │ │ interrupt_on │ │
│  │          │ │           │ │           │ │              │ │
│  └──────────┘ └───────────┘ └───────────┘ └──────────────┘ │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Tools: MCP(23个ERP工具) + Custom(5个) = 28个工具        ││
│  │ chart(26种) + websearch  + skillmanage    ││
│  │  + createdownload + queryorderinfo     ││
│  └─────────────────────────────────────────────────────────┘│
└───────────────────────────┬─────────────────────────────────┘
                            │ SSE (MCP协议)
┌───────────────────────────▼─────────────────────────────────┐
│             mcpserver (FastMCP :9000)                       │
│  httpbase.py (httpx AsyncClient 连接池)                     │
│  tools/: supplier(1) + part(3) + order(3) + inventory(1) │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP REST
┌───────────────────────────▼─────────────────────────────────┐
│             Java ERP 后端 (:8081)                             │
│             http://47.92.100.16:8081                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.5 一次完整对话的数据流

当用户在前端输入"帮我分析所有供应商的供货能力"时：

1. **前端** → POST `/api/chat/stream` (SSE)
2. **chat.py** → `agentcreator.initialize()` 确保 Agent 已创建
3. **chat.py** → `agent.astream(input, stream_mode=["messages","values","custom"])` 开始流式执行
4. **agentcreator.py** → 中间件栈依次执行 `before_agent()`（含 `HarnessPhaseMiddleware` 注入 rubric）
5. **LLM** 调用 `write_todos` → `TodoListMiddleware` 写入 `state.todos` → chat.py 从 values 流读取 → 发射 `todo_update` + `phase=planning`
6. **LLM** 决定委派给 `purchase_analyst` 子Agent
7. **子Agent** 调用 MCP 工具 → `mcpclient.py` → SSE 连接 MCP Server → `suppliertool.py` → HTTP 请求 Java ERP
8. **子Agent** 调用 `create_visual_tool` → 沙箱内 生成 chart
9. **RubricMiddleware** grader 子Agent 对照 rubric 打分 → 发射 `review_result`，needs_revision 时打回重做
10. **chat.py** → 流结束 → 保存 display_messages + harness_trace 到 MongoDB → 发射 `done` 事件

---

## 第2章 — 基础设施层

> 这一层是整个项目的基础，提供环境变量加载、数据模型定义和全局配置。所有其他模块都依赖这一层。

### 2.1 `/config` — 环境变量加载（33行）

**作用**：从项目根目录的 `.env.*`不同环境下的 文件加载环境变量到 `os.environ`。整个项目的所有配置（API Key、数据库地址等）都通过此模块加载。

```python
"""
环境变量加载工具
从项目根目录 .env 文件加载环境变量到 os.environ
"""
#配置信息
import os
from dotenv import load_dotenv
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).parent.parent
#项目的根目录加载到内存中
os.environ["BASE_DIR"] = str(BASE_DIR)


def load_env(env_name: str = None):
    """
    env_name: test / prod / dev
    加载对应的环境变量文件
    """
    env_file_map = {
        "dev": BASE_DIR / ".env",
        "test": BASE_DIR / ".env.test",
        "prod": BASE_DIR / ".env.prod",
    }

    # 如果传入环境名称，加载指定env文件
    if env_name and env_name in env_file_map:
        env_path = env_file_map[env_name]
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            print(f"已加载环境配置: {env_path.name}")
        else:
            raise FileNotFoundError(f"环境文件不存在：{env_path}")
    else:
        # 默认加载 .env（本地开发）
        load_dotenv()


# ⚡ 关键设计：模块加载时自动调用 load_env()
# 根据fastapi生命周期管理，实现在服务启动前加载配置
webcontextmanager.lifespan
```

**被谁依赖**：`config.py`、`agentconfig.py`、`websearch.py` 等几乎所有需要配置的模块。

**.env 文件内容**：
```bash
DASHSCOPE_API_KEY=sk-f99ccd929fe146629c62c7339d3a9e55
MONGODB_URI=mongodb://localhost:27017
ERP_BASE_URL=http://47.92.108.163:8081
MCP_SERVER_URL=http://localhost:9000
SANDBOX_IMAGE=opensandbox/code-interpreter:v1.0.2
```

---

### 2.2 `bean/parambean.py` — Pydantic 数据模型（含 Harness 结构化状态）

**作用**：定义整个项目中流转的数据结构。这是类型安全的保障——所有请求、响应、上下文都通过这些模型约束。**本次改造新增了 Harness 四阶段的结构化状态模型**（Phase/PlanStep/Plan/ReviewResult），替代原先靠 prompt 软约束 + 正则猜测的脆弱实现。

```python
"""
数据模型定义
RequestBean、Message、ResponseBean 等 Pydantic 模型
"""
from typing import Optional,Any,List,Dict

from datetime import datetime
from pydantic import BaseModel,Field
from requests import Session


#用户请求bean
class RequestBean(BaseModel):
    thread_id: str #会话标识id
    input: Optional[str] #用户输入内容
    resume_data: dict[str, Any]
    def __init__(self,thread_id,input,resume_data):
        super().__init__()
        self.thread_id = thread_id
        self.input = input
        self.resume_data =resume_data


class Message(BaseModel):
    """消息模型"""
    id: str = Field(..., description="消息唯一标识")
    role: str = Field(..., description="消息角色: user/assistant/tool")
    content: str = Field("", description="消息内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    tool_calls: Optional[List[Dict[str, Any]]] = Field(None, description="工具调用信息")
    tool_call_id: Optional[str] = Field(None, description="工具调用 ID")
    source: Optional[str] = Field(None, description="消息来源: main 或子代理名称")
    # 工具消息专属字段
    tool_name: Optional[str] = Field(None, description="工具名称")
    tool_status: Optional[str] = Field(None, description="工具状态: calling / done")
    text: Optional[str] = Field(None, description="工具结果文本")
    images: Optional[List[str]] = Field(None, description="工具结果图片列表")
    args: Optional[str] = Field(None, description="工具调用参数")

class ChatResponse(BaseModel):
    """对话响应模型"""
    thread_id: str = Field(..., description="会话 ID")
    messages: List[Message] = Field(default_factory=list, description="消息列表")


```

**被谁依赖**：
- 基础模型：`chat.py`（ChatRequest/ChatResponse）、`history.py`（Message）。
- Harness 模型：`harness.py`（Phase/ReviewResult）、`chat.py`（阶段/评审结构化事件）。

---

### 2.3 `config/config.py` — 全局配置（56行）

**作用**：集中管理所有配置参数。这是整个项目的"配置中心"——LLM、MongoDB、MCP、沙箱、Agent 限制等所有配置都在这里定义。

```python
"""
全局配置模块
LLM、Store、Checkpointer、沙箱连接参数
"""
import os
from langchain_openai import ChatOpenAI


# ============ LLM 配置 ============
LLM_MODEL = os.get_env("LLM_MODEL", "qwen-plus")  # 通义千问模型
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # OpenAI 兼容接口
LLM_API_KEY = os.get_env("DASHSCOPE_API_KEY", "")
LLM_TEMPERATURE = 0.1       # 低温度 → 更确定性的输出
LLM_MAX_TOKENS = 4096       # 单次最大输出 token 数


"""
    获取 LLM 实例（通义千问 OpenAI 兼容接口）
    
    设计要点：
    - 使用 ChatOpenAI 而非直接调用 DashScope SDK
    - 因为通义千问提供了 OpenAI 兼容的 API 接口
    - 这样可以用 LangChain 的统一接口，未来切换 LLM 只需改 base_url 和 api_key
"""

llm = ChatOpenAI(
    model="qwen3.7-plus",
    temperature=1.1,
    openai_api_key="sk-ws-H.REDDIIH.XSEx.MEQCIAVO0fweooUwKWxBwmETA2nFqIGVXLTT0iwVnvuNBHXVAiB-p0O7uwDYWX_K57z2jvrFMWw-bPXrjoiEDnxivwKgLg",
    openai_api_base="https://llm-jjahfel84vu866j1.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    max_tokens=131072,
    extra_body= {"enable_thinking": False})


# ============ MongoDB 配置 ============
MONGODB_URI = os.get_env("MGDB_URI", "mongodb://localhost:27017")
MONGODB_DB_NAME = os.get_env("MGDB_DATABASE_NAME", "context_db")

# ============ MCP Server 配置 ============
MCP_SERVER_URL = os.get_env("MCP_SERVER_URL", "http://localhost:9000")
MCP_SSE_URL = f"{MCP_SERVER_URL}/sse"  # MCP SSE 传输协议端点

# ============ 沙箱配置 ============
SANDBOX_DATA_PATH = "/data"       # 沙箱内工作目录
SANDBOX_SKILLS_PATH = "/skills"        # 沙箱内技能目录
SANDBOX_MEMORIES_PATH = "/memories"    # 沙箱内记忆目录

# ============ Store 命名空间 ============
# LangGraph Store 使用命名空间隔离不同类型的跨会话数据
STORE_SKILLS_NAMESPACE = ("skills",)       # 持久化技能
PREFERENCES_STORE_NAMESPACE = ("user-preferences",)  # 用户偏好

# ============ Agent 配置 ============
MAX_MODEL_CALLS = os.get_env("MAX_MODEL_CALLS", 50)  # 单次对话最大 LLM 调用次数
MAX_TOOL_CALLS = os.get_env("MAX_TOOL_CALLS", 30)    # 单次对话最大工具调用次数
SUMMARIZATION_THRESHOLD = 0.85  # 85% 上下文窗口时触发摘要压缩

# ============ 中断配置 ============
# 这些工具被调用时会自动暂停（interrupt），等待用户审批
# 这是 HITL（Human-In-The-Loop）的核心配置
INTERRUPT_ON_TOOLS = {
    "order_create": {"allowed_decisions": ["approve", "reject"]},   # 创建订单需审批
    "order_update": {"allowed_decisions": ["approve", "reject"]},   # 修改订单需审批
}
```

**设计决策**：
- 为什么 获取llm是实例而非函数？→ 每次调用都是获取同一个大模型实例
- 为什么中断只配置 `order_create` 和 `order_update`？→ 只有"写操作"需要审批，"读操作"（查询/分析）是安全的

---

## 第3章 — MCP Server 网关层

> MCP（Model Context Protocol）是一种标准协议，让 AI Agent 能以统一方式调用外部工具。本章的 MCP Server 负责把 Java ERP 的 REST API 封装为 Agent 可调用的工具。

### 3.1 `mcpserver/serverconfig.py` — ERP 后端地址配置（21行）

**作用**：定义 Java ERP 后端地址和 MCP Server 自身的监听配置。

```python
"""
MCP Server 配置模块
ERP 后端地址 + MCP 监听配置
"""
import os
from dotenv import load_dotenv

# 加载项目根目录 .env（MCP Server 独立运行，需要自己加载）
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

# Java ERP 后端地址 — 所有 MCP 工具最终都请求这个地址
ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://47.92.108.163:8081")

# MCP Server 监听配置
MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")  # 监听所有网卡
MCP_PORT = int(os.getenv("MCP_PORT", "9000"))  # MCP 默认端口 9000

# HTTP 客户端配置
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))          # 请求超时 30 秒
HTTP_MAX_CONNECTIONS = int(os.getenv("HTTP_MAX_CONNECTIONS", "20"))  # 连接池最大 20
```

**与其他模块的关系**：被 `httpbase.py` 导入使用。

---



**与其他模块的关系**：被所有 `tools/*.py` 导入使用。是 MCP 工具与 Java ERP 通信的唯一出口。

---

### 3.2 `mcpserver/interface/suppliertool.py` — 供应商工具（125行）

**作用**：将 Java ERP 的供应商管理 API 封装为 5 个 MCP 工具。

```python
"""
供应商管理 MCP 工具
supplier_query 
"""
from fastmcp import FastMCP, Context
import json

# 分组名称
GROUP_NAME = "supplier"
def register_supplier_tool(mcp: FastMCP):
    """注册供应商分组的所有工具"""

    @mcp.tool(name=f"{GROUP_NAME}_query")
    async def query_suppliers(name: str, ctx: Context) -> list:
        """
        按名称模糊搜索供应商。

        Args:
            name: 供应商名称（模糊查询），必填
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        try:
            response = await http_client.get("/suppliers/search", params={"name": name})
            response.raise_for_status()
            result = response.json()
            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]
            return result.get("data", [])
        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']

    @mcp.tool(name=f"{GROUP_NAME}_page")
    async def supplier_page(
            current: int = 1,
            size: int = 10,
            name: str = None,
            status: int = None,
            credit_rating: str = None, ctx: Context=None
    ) -> str:
        """分页查询供应商列表。

        Args:
            current: 当前页码，默认1
            size: 每页大小，默认10
            name: 供应商名称（可选，模糊匹配）
            status: 合作状态（可选）：1=合作中, 0=已停止
            credit_rating: 信用评级（可选）：A/B/C/D

        Returns:
            分页供应商数据JSON，包含 records, total, current, size, pages
        """
        params = {
            "current": current,
            "size": size,
            "name": name,
            "status": status,
            "creditRating": credit_rating,
        }
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = await http_client.get("/api/suppliers/page", params=params)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(name=f"{GROUP_NAME}_get")
    async def supplier_get(id: int,ctx: Context) -> str:
        """获取单个供应商的详细信息。

        Args:
            id: 供应商ID

        Returns:
            供应商详细信息JSON，包含 supplierCode, name, contactPerson, phone, email, address, creditRating, status
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = http_client.get(f"/api/suppliers/get/{id}")
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(name=f"{GROUP_NAME}_create")
    async def supplier_create(
            supplier_code: str,
            name: str,
            contact_person: str = None,
            phone: str = None,
            email: str = None,
            address: str = None,
            credit_rating: str = None,
            status: int = 1, ctx: Context=None
    ) -> str:
        """创建新供应商。

        Args:
            supplier_code: 供应商编码（必填）
            name: 供应商名称（必填）
            contact_person: 联系人
            phone: 联系电话
            email: 邮箱
            address: 地址
            credit_rating: 信用评级 A/B/C/D
            status: 合作状态 1=合作中 0=停止

        Returns:
            创建结果JSON
        """
        data = {
            "supplierCode": supplier_code,
            "name": name,
            "contactPerson": contact_person,
            "phone": phone,
            "email": email,
            "address": address,
            "creditRating": credit_rating,
            "status": status,
        }
        # 移除 None 值
        data = {k: v for k, v in data.items() if v is not None}
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = await http_client.post("/api/suppliers/create", json_data=data)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool(name=f"{GROUP_NAME}_update_status")
    async def supplier_update_status(id: int, status: int, ctx: Context) -> str:
        """更新供应商合作状态。

        Args:
            id: 供应商ID
            status: 新状态 1=合作中 0=已停止

        Returns:
            操作结果JSON
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")
        result = await http_client.patch(
            f"/api/suppliers/update-status/{id}", params={"status": status}
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
```

**工具清单**：
| 工具名 | HTTP 方法 | Java ERP 路径 | 用途 |
|--------|-----------|---------------|------|
| `supplier_query` | GET | `/api/suppliers/search` | 按名称搜索 |
| `supplier_page` | GET | `/api/suppliers/page` | 分页查询 |
| `supplier_get` | GET | `/api/suppliers/get/{id}` | 获取详情 |
| `supplier_create` | POST | `/api/suppliers/create` | 创建供应商 |
| `supplier_update_status` | PATCH | `/api/suppliers/update-status/{id}` | 更新状态 |

---

### 3.3 `mcpserver/interface/parttool.py` — 零部件工具（130行）

**作用**：3 个零部件管理 MCP 工具。模式与供应商工具完全相同。

```python
"""
产品/零部件管理 MCP 工具
part_query / part_search / part_by_supplier
"""
from fastmcp import FastMCP, Context
from typing import Optional

# 分组名称
GROUP_NAME = "part"   # 分组名称，最终工具名称为 part_query / part_search
def register_part_tool(mcp: FastMCP):
    """注册零部件分组的所有工具"""

    @mcp.tool(name=f"{GROUP_NAME}_query")
    async def query_parts(
        current: Optional[int] = 1,
        size: Optional[int] = 10,
        name: Optional[str] = None,
        category: Optional[str] = None,
        supplier_id: Optional[int] = None,
        ctx: Context = None,
    ) -> list:
        """
        分页查询零部件列表。
        支持按名称模糊查询、按分类筛选、按供应商ID筛选。

        Args:
            current: 当前页码，从1开始，默认1
            size: 每页大小，默认10
            name: 零件名称（模糊查询），可选
            category: 分类(发动机类/车架类/电气类/制动类/传动类/外观件)，可选
            supplier_id: 供应商ID，可选
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        # 构建请求参数（过滤 None 值，映射到 API 字段名）
        request_params = {}
        if current is not None:
            request_params["current"] = current
        if size is not None:
            request_params["size"] = size
        if name is not None:
            request_params["name"] = name
        if category is not None:
            request_params["category"] = category
        if supplier_id is not None:
            request_params["supplierId"] = supplier_id

        try:
            response = await http_client.get("/parts/page", params=request_params)
            response.raise_for_status()
            result = response.json()

            # 检查业务状态码
            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]

            # 返回 data 字段，通常包含 records, total, current, size 等
            return result.get("data", {}).get("records", [])

        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']

    @mcp.tool(name=f"{GROUP_NAME}_search")
    async def search_parts(name: str, ctx: Context) -> list:
        """
        按名称搜索零部件。
        与 part_query 不同，此接口直接搜索，name 为必填参数。

        Args:
            name: 零件名称（模糊查询），必填
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        try:
            response = await http_client.get("/parts/search", params={"name": name})
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]

            # data 为数组
            return result.get("data", [])
        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']

    @mcp.tool(name=f"{GROUP_NAME}_by_supplier")
    async def list_parts_by_supplier(supplier_id: int, ctx: Context) -> list:
        """
        根据供应商 ID 查询该供应商下有采购记录的零配件列表。

        Args:
            supplier_id: 供应商 ID（路径参数，必填）
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        try:
            response = await http_client.get(f"/parts/supplier/{supplier_id}")
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]

            return result.get("data", [])
        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']
```

---

### 3.4 `mcpserver/interface/ordertool.py` — 订单工具（169行）

**作用**：3 个采购订单管理 MCP 工具。这是最复杂的工具组，因为订单涉及创建、修改、状态变更等写操作。

```python
"""
采购订单管理 MCP 工具
order_create / order_update  / order_search_details 
"""
import random
from datetime import datetime
from decimal import Decimal

from fastmcp import FastMCP, Context

from typing import Optional, List

GROUP_NAME = "order"


def _generate_order_number() -> str:
    """生成订单编号：PO + 年月日(8位) + 3位随机数字"""
    today = datetime.now().strftime("%Y%m%d")
    suffix = str(random.randint(0, 999)).zfill(3)
    return f"PO{today}{suffix}"


def _prepare_request(data: dict) -> dict:
    """填充默认值并序列化请求体：Decimal→float，date→ISO字符串"""
    # 自动生成 orderNumber
    if not data.get("orderNumber"):
        data["orderNumber"] = _generate_order_number()

    # 默认 orderTime（格式：yyyy-MM-ddTHH:mm:ss.SSS，匹配后端 CustomLocalDateTimeDeserializer）
    if not data.get("orderTime"):
        now = datetime.now()
        data["orderTime"] = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}"

    # 递归序列化
    return _serialize_request(data)


def _serialize_request(data: dict) -> dict:
    """递归处理：Decimal → float，date/datetime → ISO 字符串"""
    for key, value in data.items():
        if isinstance(value, Decimal):
            data[key] = float(value)
        elif hasattr(value, "isoformat"):
            data[key] = value.isoformat()
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _serialize_request(item)
        elif isinstance(value, dict):
            _serialize_request(value)
    return data


def register_order_tool(mcp: FastMCP):
    """注册订单分组的所有工具"""

    @mcp.tool(name=f"{GROUP_NAME}_create")
    async def create_order(
        order_detail: List[dict],
        order_number: Optional[str] = None,
        total_amount: Optional[float] = None,
        status: Optional[int] = None,
        order_time: Optional[str] = None,
        expected_delivery_date: Optional[str] = None,
        actual_delivery_date: Optional[str] = None,
        created_by: Optional[int] = None,
        remark: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        创建采购订单（POST /orders/create）。

        orderNumber 不传则自动生成（规则：PO+年月日+3位随机数字）。
        orderTime 不传则默认当前时间（格式：yyyy-MM-ddTHH:mm:ss.SSS）。
        orderDetail 必填，至少包含一个明细项；每项需提供 partId、quantity、unitPrice。

        Args:
            order_detail: 订单明细列表，每项需提供 partId, quantity, unitPrice，可选 subtotal, remark
            order_number: 订单编号（唯一标识），不传则自动生成
            total_amount: 订单总金额，不传则自动根据明细计算
            status: 订单状态(1-待审核, 2-已审核, 3-采购中, 4-已入库, 5-已取消)，默认1
            order_time: 下单时间，格式 yyyy-MM-ddTHH:mm:ss.SSS，不传则默认当前时间
            expected_delivery_date: 预计交货日期，格式 yyyy-MM-dd
            actual_delivery_date: 实际交货日期，格式 yyyy-MM-dd
            created_by: 创建人 ID
            remark: 备注
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        # 构建请求体（映射到 API 字段名）
        request_data = {}
        if order_number is not None:
            request_data["orderNumber"] = order_number
        if total_amount is not None:
            request_data["totalAmount"] = total_amount
        if status is not None:
            request_data["status"] = status
        if order_time is not None:
            request_data["orderTime"] = order_time
        if expected_delivery_date is not None:
            request_data["expectedDeliveryDate"] = expected_delivery_date
        if actual_delivery_date is not None:
            request_data["actualDeliveryDate"] = actual_delivery_date
        if created_by is not None:
            request_data["createdBy"] = created_by
        if remark is not None:
            request_data["remark"] = remark
        if order_detail is not None:
            request_data["orderDetail"] = order_detail

        request_data = _prepare_request(request_data)

        try:
            print(request_data)
            response = await http_client.post(
                "/orders/create",
                json=request_data
            )
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 200:
                return {
                    "error": f"API error: code={result.get('code')}, message={result.get('message')}"
                }

            return result.get("data", {})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool(name=f"{GROUP_NAME}_update")
    async def update_order(
        order_id: int,
        order_detail: Optional[List[dict]] = None,
        order_number: Optional[str] = None,
        total_amount: Optional[float] = None,
        status: Optional[int] = None,
        order_time: Optional[str] = None,
        expected_delivery_date: Optional[str] = None,
        actual_delivery_date: Optional[str] = None,
        created_by: Optional[int] = None,
        remark: Optional[str] = None,
        ctx: Context = None,
    ) -> dict:
        """
        更新采购订单（PUT /orders/update/{id}）。

        orderDetail 为可选，传入则替换原有明细。
        其他字段与创建订单格式一致。

        Args:
            order_id: 订单 ID（路径参数，必填）
            order_detail: 订单明细列表（可选），每项需提供 partId, quantity, unitPrice
            order_number: 订单编号
            total_amount: 订单总金额
            status: 订单状态(1-待审核, 2-已审核, 3-采购中, 4-已入库, 5-已取消)
            order_time: 下单时间
            expected_delivery_date: 预计交货日期
            actual_delivery_date: 实际交货日期
            created_by: 创建人 ID
            remark: 备注
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        # 构建请求体（映射到 API 字段名，只包含非 None 字段）
        request_data = {}
        if order_number is not None:
            request_data["orderNumber"] = order_number
        if total_amount is not None:
            request_data["totalAmount"] = total_amount
        if status is not None:
            request_data["status"] = status
        if order_time is not None:
            request_data["orderTime"] = order_time
        if expected_delivery_date is not None:
            request_data["expectedDeliveryDate"] = expected_delivery_date
        if actual_delivery_date is not None:
            request_data["actualDeliveryDate"] = actual_delivery_date
        if created_by is not None:
            request_data["createdBy"] = created_by
        if remark is not None:
            request_data["remark"] = remark
        if order_detail is not None:
            request_data["orderDetail"] = order_detail

        request_data = _prepare_request(request_data)

        try:
            print(request_data)
            response = await http_client.put(
                f"/orders/update/{order_id}",
                json=request_data
            )
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 200:
                return {
                    "error": f"API error: code={result.get('code')}, message={result.get('message')}"
                }

            return result.get("data", {})
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool(name=f"{GROUP_NAME}_search_details")
    async def search_order_details(
        part_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        ctx: Context = None,
    ) -> list:
        """
        搜索采购订单明细。

        支持按零部件名称、日期范围筛选，所有参数均为可选。
        返回的每条明细包含零部件详情（partDetail）及供应商信息（supplier）。

        Args:
            part_name: 零部件名称（模糊查询），可选
            start_date: 开始日期（yyyy-MM-dd 格式），可选
            end_date: 结束日期（yyyy-MM-dd 格式），可选
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        # 构建请求参数（过滤 None 值，映射到 API 字段名）
        request_params = {}
        if part_name is not None:
            request_params["partName"] = part_name
        if start_date is not None:
            request_params["startDate"] = start_date
        if end_date is not None:
            request_params["endDate"] = end_date

        try:
            response = await http_client.get(
                "/orders/search-details",
                params=request_params
            )
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]

            return result.get("data", [])
        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']
```

---

### 3.5 `mcpserver/interface/inventorytool.py` — 库存工具（114行）

**作用**：6 个库存管理 MCP 工具。

```python
"""
库存管理 MCP 工具
inventory_warning 
"""
from fastmcp import FastMCP, Context

GROUP_NAME = "inventory"


def register_inventory_tool(mcp: FastMCP):
    """注册库存管理分组的所有工具"""

    @mcp.tool(name=f"{GROUP_NAME}_warning")
    async def list_inventory_warnings(ctx: Context) -> list:
        """
        查询库存预警列表。
        返回所有库存不足（当前库存低于安全库存）的物料及对应的零部件详情。

        无需传参。
        """
        http_client = ctx.request_context.lifespan_context.get("http_client")

        try:
            response = await http_client.get("/inventory/warning")
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 200:
                return [f"API error: code={result.get('code')}"]

            return result.get("data", [])
        except Exception as e:
            return [f'没有查询到任何信息，而且报错: {e}']
```

---

### 3.6 `mcpserver/server.py` — FastMCP 入口（34行）

**作用**：创建 FastMCP 实例，注册所有工具，以 SSE 传输协议启动。

```python
"""
MCP Server 入口
FastMCP 实例创建，注册所有 tools，SSE 传输协议
"""
from fastmcp import FastMCP
# 导入各个分组的注册函数
from mcpserver.interface.suppliertool import register_supplier_tool
from mcpserver.interface.parttool import register_part_tool
from mcpserver.interface.ordertool import register_order_tool
from mcpserver.interface.inventorytool import register_inventory_tool
from mcpserver.serverconfig import MCP_HOST, MCP_PORT, MCP_PATH
from mcpserver.httpbase import mcp_lifespan

mcp=FastMCP(name="",instructions="调用Java后端具体业务数据接口"
            ,version="1.0.0",
            language="Java",
            lifespan=mcp_lifespan
            )

# 注册所有分组
register_supplier_tool(mcp)
register_part_tool(mcp)
register_order_tool(mcp)
register_inventory_tool(mcp)


def main():

    # 启动 Streamable HTTP 服务
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH
    )
    # 注意：run() 会阻塞，且 lifespan 会在服务器关闭时自动清理资源


if __name__ == "__main__":
    main()
```

**MCP 协议工作原理总结**：
1. MCP Server 启动后监听 `:9000/sse`，提供 SSE 连接
2. Agent 的 `mcpclient.py` 通过 `MultiServerMCPClient` 连接 SSE
3. 连接建立后，Agent 获取所有 23 个工具的 schema（名称、参数、描述）
4. Agent 调用工具时，MCP Server 执行对应的 async 函数 → HTTP 请求 Java ERP → 返回 JSON 结果

---

## 第4章 — Agent 工具层

> 除了 MCP 提供的 23 个 ERP 工具外，Agent 还有 9 个自定义工具：图表生成（沙箱内）、文档生成（沙箱内）、网络搜索、URL 抓取、Skill 安装（沙箱隔离流程）、人工介入、技能分配、沙箱文件下载、沙箱文件列表。
> 
> ⚠️ **核心安全原则**：所有涉及代码执行和文件生成的操作（图表/文档/Skill安装）都必须在 Docker 沙箱内进行，宿主机只运行 Agent 框架本身。



---

## 附录 — 完整执行流程

### A.1 一次对话的完整调用链

用户输入："帮我分析所有供应商的供货能力"

```
1. 前端 → POST /api/chat/stream {message: "帮我分析...", user_id: "user-001"}
2. web_main.py → chat_router → chat_stream()
3. chat.py → agent_loader.initialize() → 确保 Agent 已创建
4. chat.py → stream_chat_response() → yield thinking(start)
5. chat.py → agent.astream(input, stream_mode=["messages","values"])
6. main_agent.py → 中间件 before_agent() 依次执行:
   ① SandboxHealthMiddleware → ping 沙箱
   ② ContextInjectionMiddleware → 注入 user_id/preferences
   ③ SkillsSyncMiddleware → 同步技能文件
   ④ UserSkillsRestoreMiddleware → 恢复持久化技能
   ⑤ ToolsSummarizationMiddleware → 检查上下文长度
7. LLM 输出 Planning 文本
8. chat.py → 正则检测 → yield phase(planning) + todo_update
9. LLM 决定委派 → tool_call: task(agent="procurement-analyst")
10. chat.py → yield tool_start + tool_args
11. 子Agent 开始执行:
    ① supplier_page(size=100) → MCP → HTTP → Java ERP → 返回供应商列表
    ② generate_chart(bar, data) → matplotlib → PNG
    ③ 输出分析报告
12. chat.py → yield token(子Agent的token) + tool_result
13. LLM 输出 Review + Result
14. chat.py → yield phase(reviewing) + phase(done)
15. 中间件 after_agent():
    ⑥ MemoryUpdateMiddleware → 提取偏好 → store.put()
16. chat.py → save_display_messages() → MongoDB
17. chat.py → save_conversation() → MongoDB
18. chat.py → yield done(thread_id, interrupted=False)
```

### A.2 启动命令与依赖关系

```bash
# 启动顺序（严格按依赖）
# 1. MongoDB（Docker）
docker start erp-mongo

# 2. MCP Server（无外部依赖，先启动）
python -m uvicorn src.mcp_server.server_main:app --port 9000

# 3. Web API Server（依赖 MCP Server + MongoDB）
python -m uvicorn src.api_view.web_main:app --port 8000

# 4. Frontend（依赖 Web API）
cd frontend && npm run dev
```

### A.3 中间件执行时序图

```
用户请求
    │
    ▼
┌─────────────────────────────┐
│ ① SandboxHealthMiddleware   │  before_agent: ping 沙箱
├─────────────────────────────┤
│ ② ContextInjectionMiddleware│  before_agent: 注入用户上下文
├─────────────────────────────┤
│ ③ SkillsSyncMiddleware      │  before_agent: 同步技能
├─────────────────────────────┤
│ ④ UserSkillsRestore         │  before_agent: 恢复持久化技能
├─────────────────────────────┤
│ ⑤ Summarization             │  before_agent: 检查上下文长度
├─────────────────────────────┤
│ ⑥ MemoryUpdate              │  after_agent: 提取偏好
├─────────────────────────────┤
│ ⑦ SandboxCircuitBreaker     │  wrap_tool_call: 熔断保护
├─────────────────────────────┤
│ ModelCallLimit              │  框架内置: LLM 调用上限
├─────────────────────────────┤
│ ToolCallLimit               │  框架内置: 工具调用上限
└─────────────────────────────┘
    │
    ▼
  Agent 执行
```

### A.4 HITL 中断/恢复流程

```
用户: "帮我创建一个采购订单"
    │
    ▼
主Agent → 委派 procurement-order
    │
    ▼
子Agent → 提取订单信息 → 发现缺少 partId
    │
    ▼
子Agent → 调用 request_order_info()
    │
    ▼
hitl_tools.py → interrupt({type: "order_info_request", missing: ["partId"]})
    │
    ▼
LangGraph 暂停执行
    │
    ▼
chat.py → 检测 values.interrupts → yield SSE interrupt 事件
    │
    ▼
前端 → 显示补充信息输入框
    │
    ▼
用户输入: "零件ID=5 数量100 单价25.5"
    │
    ▼
前端 → POST /api/chat/{thread_id}/resume {supplement: "零件ID=5..."}
    │
    ▼
chat.py → stream_chat_response(resume_data=...) → Command(resume=...)
    │
    ▼
LangGraph 恢复执行 → interrupt() 返回用户输入
    │
    ▼
hitl_tools.py → parse_supplement_text() → validate_order_data() → 数据完整
    │
    ▼
子Agent → 调用 order_create() → 触发 interrupt_on 审批中断
    │
    ▼
前端 → 显示审批卡片 → 用户点击"批准"
    │
    ▼
前端 → POST /resume {decisions: [{type: "approve"}]} → 订单创建成功
```

---

## 总结

本文档按照「基础设施 → MCP网关 → 工具层 → 沙箱 → 中间件 → 子Agent → 记忆 → 核心组装 → Web API」的顺序，逐文件解析了整个 Python 后端代码。

**核心文件阅读顺序推荐**：
1. `config.py` → 了解所有配置
2. `main_agent.py` → 了解 Agent 如何组装（含沙箱初始化、Skills 加载、Harness 中间件）
3. `harness.py` → ★了解 Harness 阶段状态机 + rubric 注入 + 评审回路
4. `harness_config.yaml` → ★了解声明式工作流配置（四阶段/评审标准）
5. `custom_opensandbox.py` → 了解沙箱后端（30+ 方法、文件操作、多语言运行时）
6. `sandbox_holder.py` → 了解工具如何全局访问沙箱
7. `chart_generator.py` → 了解沙箱内代码执行模式
8. `chat.py` → 了解 SSE 流式对话 + 结构化阶段读取
9. `skills_sync.py` → 了解技能增量同步机制

**关键设计模式**：
- **Harness 工作流**：Planning → Executing → Review → Result 已从 prompt 软约束升级为 graph state 结构化字段（`HarnessPhaseMiddleware`）+ 评审回路（`RubricMiddleware`）
- **沙箱优先**：所有代码执行/文件生成强制在 Docker 沙箱内，宿主机只跑框架
- **中间件栈**：可扩展的 before/after/wrap 钩子
- **CompositeBackend**：路径路由到不同后端
- **MCP 协议**：统一工具调用接口
- **HITL**：interrupt/resume 实现人工审批
- **熔断器**：三态模型保护沙箱调用
- **sandbox_holder**：全局单例，工具通过 `get_sandbox()` 访问沙箱
- **评审回路**：grader 子 Agent 对照 rubric 打分，needs_revision 自动打回重做
- **可观测 trace**：阶段流转 + 评审判定持久化到 MongoDB



**架构转变核心**：

| 维度 | 旧版 | 新版 |
|------|------|------|
| Phase | 正则猜 LLM 文本 | `state.phase`（图状态，checkpoint 持久化） |
| Todo | 正则提编号列表 | `state.todos`（`TodoListMiddleware` 结构化） |
| Review | LLM 自述"审查" | `RubricMiddleware` grader 子 Agent 打分 + 打回回路 |
| output_format | 仅 YAML 声明 | 契约校验 + 注入 + 评审器校验 |
| 可观测 | 无 | `harness_traces` MongoDB 持久化 |

**阶段流转机制**：
```
before_agent  → phase=planning（注入 rubric）
after_model   → phase=executing（模型调用工具时）
after_agent   → phase=reviewing（needs_revision 打回重做）
              → phase=result（satisfied/failed/超限）
```
