import os
from pathlib import Path

from langchain.agents import AgentState
from langchain.agents.middleware import ToolCallLimitMiddleware, ModelCallLimitMiddleware, OutputAgentState, \
    InputAgentState
from langchain_core.runnables import RunnableConfig
from typing import Optional, Any

from langgraph.graph.state import CompiledStateGraph

from agent.sandbox.sandboxcreator import create_sandbox

from deepagents.backends import CompositeBackend, StoreBackend

from bean.parambean import PurchaseContext
from mcpclient.mcpclient import McpClient,MCP_NAMES

from tools.skillmanagetool import SkillManageTool

from tools.createvisualtool import CreateVisualTool
from tools.createdownloadtool import CreateDownloadTool

from tools.websearchtool import web_search_tool

from tools.queryorderinfotool import query_order_info_tool

from middlewares.middlewarefactory import analyst_middleware, order_middleware, ContextInjectionMiddleware, \
    UpdateMemoryMiddleware, SyncSkillsMiddleware, RestoreSkillsMiddleware, summarization_tool_middleware

from subagents.subagentcreator import SubAgentCreator

from deepagents import create_deep_agent

from llm.my_llm import llm

from agentconfig import system_prompt, redis_store, checkpointer


MCP_NAMES=["erp-api","analysis"]

class AgentCreator:

    __instance:Optional['AgentCreator']

    _deep_agent:CompiledStateGraph=None

    # 是否已初始化
    _initialized= False

    ###创建实例
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self):
        if self._initialized and self._deep_agent is not None:
            return

        self._deep_agent = await self.get_deep_agent()

        self._initialized = True

        print("[AgentCreator] 初始化完成!!!!!")

    @property
    def deep_agent(self):
        if self._deep_agent is None:
            raise RuntimeError("Agent 未初始化，请先调用 initialize() 方法")
        return self._deep_agent

    @property
    def instance(self):
        return self.__instance


    def add_sandbox(self):
        pass


    async def get_deep_agent(self,config: Optional[RunnableConfig] = None,*,
    sandbox_id: Optional[str] = None)-> CompiledStateGraph[AgentState, Any, InputAgentState, OutputAgentState]:


        # self._agent = await _create_agent()
        sandboxbackend=create_sandbox(config,sandbox_id)

        ##AGENTS.MD文件是否上传至沙箱这一步待确定(智能体的定义信息，每次请求时整合至prompt中)
        agents_md_content=Path(os.getenv("BASE_DIR") + os.getenv("LOCAL_AGENTS_MD")).read_text(encoding="utf-8")
        sandboxbackend.upload_files([("/AGENTS.md",agents_md_content.encode("utf-8"))])


        #创建路径路由 backend CompositeBackend
        composite_backend=lambda rt:CompositeBackend(default=sandboxbackend, routes={"/memories/":StoreBackend(rt,namespace=(getattr(rt.context,"user_id","xej"),)),
                                                         "/persisted-skills/":StoreBackend(rt,namespace=(getattr(rt.context,"user_id","xej"),))})

        ##获取MCP所有工具
        mcp_client=McpClient()
        start_with_rule_list ={
            mcp_client.ORDER_TOOL_PREFIX:[],
            mcp_client.CHART_TOOL_PREFIX: [],
        }
        analyst_tool=[]#分析工具
        all_tool=[] #erp系统工具
        for mcp_name in MCP_NAMES:
            tools = mcp_client.get_mcp_tools(mcp_name)
            all_tool.extend(tools)
            if(mcp_name=="analysis"):
                start_with_rule_list[mcp_client.CHART_TOOL_PREFIX].extend(tools)
                continue

            if not tools:
                for tool in tools:
                    if tool.name.startswith(mcp_client.ORDER_TOOL_PREFIX):
                        start_with_rule_list[mcp_client.ORDER_TOOL_PREFIX].extend(tool)
                    else:
                        analyst_tool.extend(tool)

        #获取视图和独立留存工具
        create_visual_tool=CreateVisualTool()

        create_visual_tool, separate_mcp_tools=create_visual_tool.handle_tools(start_with_rule_list.get(mcp_client.CHART_TOOL_PREFIX))

        ##STORE_SKILLS_NAMESPACE
        ##获取分配skill的工具
        assign_skills_tool=SkillManageTool.assign_skills(sandboxbackend,os.getenv("STORE_SKILLS_NAMESPACE"))

        ##创建下载工具
        download_tool=CreateDownloadTool.create_download_tool(sandboxbackend,os.getenv("BASE_DIR")+os.getenv("DOWNLOAD_DIR"))

        ##所有工具集合
        all_tools=list(start_with_rule_list.get(mcp_client.ORDER_TOOL_PREFIX))+ analyst_tool+separate_mcp_tools+[create_visual_tool]+[assign_skills_tool]+[download_tool]+[web_search_tool]+[query_order_info_tool]

        ##加载子agent配置信息

        ##子agent的中间键
        sub_middleware = {
            "purchase-analyst": analyst_middleware,
            "purchase-order": order_middleware,
        }

        ##获取subagents
        sub_agent_creator=SubAgentCreator()
        subagents=sub_agent_creator.get_sub_agents(
            tools=all_tools,
            sub_middleware=sub_middleware,
        )

        #主agent的中间件
        main_middleware=[
            RestoreSkillsMiddleware(sandboxbackend, os.getenv("STORE_SKILLS_NAMESPACE")),
            SyncSkillsMiddleware(sandboxbackend),
            UpdateMemoryMiddleware(model=llm),
            summarization_tool_middleware(composite_backend, llm),
            ModelCallLimitMiddleware(thread_id=50),
            ContextInjectionMiddleware(),
            ToolCallLimitMiddleware(thread_id=50),

        ]

        deep_agent=create_deep_agent(
            model=llm,
            tools=[download_tool,web_search_tool,assign_skills_tool],
            system_prompt=system_prompt,
            memory=[os.getenv("LOCAL_AGENTS_MD")],
            subagents=subagents,
            backend=composite_backend,
            store=redis_store,
            context_schema=PurchaseContext,
            skills=["/skills/manage/"],
            checkpointer=checkpointer,
            middleware=main_middleware
        )

        return deep_agent
