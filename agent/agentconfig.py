import os
from typing import Dict

from langchain_community.storage import RedisStore
from pymongo import MongoClient
from redis.client import Redis
from langchain_community.storage import MongoDBSaver

#获取agent相关配置
def get_config(thread_id:str,user_id:str,**kwargs)->Dict:
    return {"configurable":{
            "thread_id":thread_id,
            "user_id":user_id,
            **kwargs
            }}


def get_redis_client()->Redis:
    return Redis.from_url(os.getenv("REDIS_URL",default="redis://localhost:6379"))


redis_store=RedisStore(client=get_redis_client(),namespace="purchase_agent")

mongo_client=MongoClient(os.getenv("MONGODB_URL",default="mongodb://localhost:27017/"))
checkpointer = MongoDBSaver(
    client=mongo_client,
    db_name=os.getenv("MGDB_DATABASE_NAME",default="context_db"),
    checkpoint_collection_name=os.getenv("MGDB_CHECKPOINTER_COLLECTION",default="purchase_agent"),
)


# subAgent名称 → 技能 scope 目录映射
AGENT_SCOPE_MAP = {
    "manage": "manage",
    "purchase-analyst": "purchase",
    "purchase-order": "order",
}






"""
主 Agent 系统提示词。

此提示词作为 create_deep_agent(system_prompt=...) 的参数传入。
详细的完整行为准则见 /memories/AGENTS.md（通过 memory 参数加载）。
"""

system_prompt = """
你是 ERP 采购智能助手，负责协调专业的子 Agent 完成采购任务。

## 你的角色
你是**协调者**，不是执行者。分析类和订单类任务必须委派子 Agent，不要直接调用 MCP 业务工具。
- 采购分析 → 委派 `procurement-analyst`
- 订单操作（创建/修改/查询） → 委派 `procurement-order`
- 简单问候或功能询问 → 直接回复

## 启动时
1. 当前用户信息（user_id、username、偏好文件路径）已注入到上方 system prompt 中
2. 使用 `read_file` 读取偏好文件获取用户偏好
3. 如果文件不存在 → 使用 `write_file` 创建默认偏好文件（preferred_output: chart, preferred_chart_type: bar, preferred_currency: CNY, preferred_language: zh），然后继续工作

## 委派任务时
使用 `task` 工具，`description` 中必须包含：【任务目标】【用户偏好】【需求正文】
子 Agent 返回长篇报告后，**立即调用 `compact_conversation`** 压缩上下文。

## 对话中
- 用户表达新偏好（如"以后都用表格"）→ 更新 `/memories/{user_id}/preferences.md`
- 所有结论基于子 Agent 返回的真实数据，绝不编造
- 子 Agent 执行失败时，如实向用户说明并询问是否重试

## 详细规则
完整的行为准则、委派模板、记忆格式、安全边界见 `/AGENTS.md`，你必须始终遵守。
"""