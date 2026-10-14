import asyncio
import hashlib
from datetime import timezone,datetime
from numbers import Number
from pathlib import Path

from deepagents.backends import CompositeBackend
from deepagents.backends.sandbox import BaseSandbox
from deepagents.middleware import create_summarization_tool_middleware, SummarizationToolMiddleware
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware, AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, BaseMessage
from langgraph.store.base import BaseStore
from pydantic import json

#中间件工厂

from llm.my_llm import llm

from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from typing import Any, Dict, Tuple, Union

import os

# 跳过更新的无意义消息模式
_FILTER_WORDS = [
    "你好", "在吗", "嗨", "hello", "hi", "hey",
    "你能做什么", "你有哪些功能", "你是谁",
    "我之前的偏好", "我的偏好", "我的记忆",
]

#包含的关键字
_KEYWORDS = [
    "供应商", "物料", "采购", "订单", "价格", "分析", "对比",
    "比价", "报价", "评估", "筛选", "推荐", "行情", "预算",
    "库存", "交货", "交期", "质量", "成本", "报价", "招标",
    "supplier", "part", "order", "price", "analysis",
]

def analyst_middleware(backend):
    """
     分析师中间件
     summarization_tool_middleware:摘要中间件。会创建被动和主动两个中间件
     ModelCallLimitMiddleware：模型调用中间件，监控代理的调用模型的次数分为线程级和运行级
     ToolCallLimitMiddleware:工具 调用次数控制中间件
    :return:
    """
    return [
        create_summarization_tool_middleware(model=llm, backend=backend),
        ModelCallLimitMiddleware(thread_limit=50),
        ToolCallLimitMiddleware(thread_limit=50),
    ]


def order_middleware(backend):
    return [ModelCallLimitMiddleware(thread_limit=50),
        ToolCallLimitMiddleware(thread_limit=50),]



def summarization_tool_middleware(backend: CompositeBackend,
    model: Union[str, BaseChatModel] = "qwen3.7-plus",)-> SummarizationToolMiddleware:
    """
     SummarizationToolMiddleware:摘要工具中间件，该中间件依托于SummarizationMiddleware中间件。所以在创建SummarizationToolMiddleware
     中间件时内部会创建一个SummarizationMiddleware中间件。因为SummarizationMiddleware时自动压缩 当 token 超过触发阈值开始自动压缩
     而SummarizationToolMiddleware手动压缩。它是一个工具式摘要中间件，它**不做 before_model 自动检测**，它的唯一作用：**注册一个`compact_conversation`工具给 Agent
     Agent 在合适时机（比如调研任务结束、准备开启新物料价格调研）主动调用这个工具。
     1. `create_summarization_tool_middleware()`：内部先创建 SummarizationMiddleware，再包装成 SummarizationToolMiddleware，一次性拿到「自动兜底 + 可手动调用工具」两层能力

    :param backend:
    :param model:
    :return:
    """

    return  create_summarization_tool_middleware(
        model=model,
        backend=backend,
    )


#上下文注入中间件
class ContextInjectionMiddleware(AgentMiddleware):

    def before_agent(self, state: Dict[str,Any], runtime: Runtime[ContextT]) -> dict[str, Any] | None:

        #获取 上下文
        context=getattr(runtime, "context",None)

        if context is None:
            return None

        #获取当前会话的用户id
        user_id=getattr(context, "user_id", None)
        if not user_id:
            return None

        #获取用户名
        user_name = getattr(context, "user_name", None)

        content={
            f"【系统上下文】\n",
            f"当前用户 user_id:{user_id}\n",
            f"当前用户名username:{user_name}",
            f"用户偏好文件路径：/memories/{user_id}/prefence",
            f"\n 请首先使用read_file 读取上诉偏好文件 了解用户偏好",
            f"\n(recent_suppliers和 recent_queries 由系统自动维护，无需手动更新)"
        }
        return {"message":[SystemMessage(content=content)]}

    async def abefore_model(self, state: Dict[str, Any], runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        # 调同步函数
        return await asyncio.to_thread(self.before_agent, state, runtime)


#同步技能文件中间件
class SyncSkillsMiddleware(AgentMiddleware):


    def __init__(self, backend:BaseSandbox):
        super().__init__()

        self.backend = backend

        #本地技能文件内存的hash值缓存起来，做对比，监控文件内容是否有变化
        self.__local_skill_content_cache=Dict[str,str]


    def before_agent(self, state: Dict[str, Any], runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        sync_skills = self._sync_files()
        if sync_skills:
            return self.__get_message(sync_skills)
        return None

    async def abefore_agent(
        self, state: Dict[str, Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        import asyncio
        loop = asyncio.get_running_loop()
        sync_skills = await loop.run_in_executor(None, self._sync_files)
        if sync_skills:
            return self.__get_message(sync_skills)
        return None


    def __get_message(self,skills:list[str]):
        skill_names="\n".join(f"- {name}" for name in skills)
        content = (
            f"[系统通知] 以下技能包已更新：\n{skill_names}\n"
            "请使用 `ls /skills/` 查看详情，对当前任务可能有帮助。"
        )
        return {"messages": [SystemMessage(content=content)]}

    def __sync_files(self)->list[str]:
        #本地skill的位置
        local_skills_path=Path(os.getenv("BASE_DIR")+os.getenv("LOCAL_SKILLS_PATH"))

        if not local_skills_path.exists():
            return []

        updated_skills: list[str] = None

        for sub_dir in local_skills_path.iterdir():
            #不是文件夹了直接跳过
            if not sub_dir.is_dir():
                continue

            #按理说这应该是文件
            skill_dir_name=sub_dir.name

            #沙箱内skill文件存放路径
            sandbox_skill_path=f'{os.getenv("SANDBOX_SKILLS_PATH")}/{skill_dir_name}'

            #sub_dir 本地技能目录下，获取子目录下的技能文件内容
            for local_skill_file in sub_dir.rglob("*"):
                if not local_skill_file.is_file():
                    #不是技能文件的则直接跳过
                    continue
                #/1/2/3/4.txt 相对/1/2 截取后==>变成/3/4.txt
                relative_parent_path=local_skill_file.relative_to(sub_dir).as_posix()

                ##拼接在沙箱内的文件地址
                sandbox_skill_file=f'{sandbox_skill_path}/{relative_parent_path}'

                with open(local_skill_file, "rb") as f:
                    local_skill_content=f.read()

                local_skill_content_md5=hashlib.md5(local_skill_content).hexdigest()
                cache_key=f"{skill_dir_name}/{relative_parent_path}"

                if self.__local_skill_content_cache.get(cache_key) and self.__local_skill_content_cache.get(cache_key) ==local_skill_content_md5:
                    continue
                try:
                    # 判断沙盒中的文件是否存在
                    resp = self.backend.execute(f"test -f {sandbox_skill_file}")
                    if resp.exit_code == 0:
                        resps = self.backend.download_files(sandbox_skill_file)
                        if resps and resps[0].content and not resps[0].error:
                            sand_skill_content=resps[0].content
                            if isinstance(sand_skill_content, str):
                                sand_skill_content_md5=hashlib.md5(sand_skill_content.encode("utf-8")).hexdigest()
                                if local_skill_content_md5 == sand_skill_content_md5:
                                    self._last_hashes[cache_key] = local_skill_content_md5
                                    continue
                except Exception as e:
                    print("同步技能文件异常：\n{}".format(e))

                self.backend.upload_files([{sandbox_skill_file,local_skill_content}])

                if updated_skills is None:
                    updated_skills=[]
                updated_skills.append(skill_dir_name)

        return updated_skills



##从将持久化的技能恢复到沙箱中
class RestoreSkillsMiddleware(AgentMiddleware):

    def __init__(self, backend:BaseSandbox,skills_namespace):
        super().__init__()
        self.backend = backend
        self.skills_namespace=skills_namespace


    def before_agent(self, state: Dict[str,Any], runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """Logic to run before the agent execution starts.

        Args:
            state: The current agent state.
            runtime: The runtime context.

        Returns:
            Agent state updates to apply before agent execution.
        """


        return None



    async def abefore_agent(
        self, state: Dict[str,Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        """Async logic to run before the agent execution starts.

        Args:
            state: The current agent state.
            runtime: The runtime context.

        Returns:
            Agent state updates to apply before agent execution.
        """
        # 从运行时对象中获取store对象
        store = runtime.store

        skills = await self.__get_skills(store)

        if skills:
            #上传skill文件到沙箱
            await self.backend.aupload_files(skills)
        return None



    async def __get_skills(self,store: BaseStore) -> list[Tuple[str, bytes]] | None:

        try:
            elements=await store.asearch(self.skills_namespace)
        except:
            return []
        skills:list[Tuple[str, bytes]]=None
        for element in elements:

            value = element.value

            if not value:
                continue

            #将key包含‘/’的左边数据都截取掉，如：'/ab/ad/ab'.lstrip('/ab')===>d/ab
            #`lstrip("/ab")` 的参数是字符集合，不是要删除固定前缀字符串,而是从字符串最左侧，逐个字符，只要这个字符存在于集合 `{'/','a','b'}` 里面，就删掉；遇到不在集合里的字符，立刻停止。

            path=str(element).lstrip("/")

            #按照‘/’分割，最大分割1次，因此会得到2个元素
            paths=path.split(sep="/",maxsplit=1)

            if len(paths) != 2:
                continue

            front_part, last_part = paths
            sandbox_path = f"/skills/{front_part}/{last_part}"

            if isinstance(value, dict):
                value = value.get("content", "")
            if isinstance(value, str):
                value = value.encode("utf-8")

            if skills is None:
                skills=[]

            skills.append((front_part, value))

        return skills





#更新用户记忆文件 recent_suppliers / recent_queries。中间件
class UpdateMemoryMiddleware(AgentMiddleware):


    def __init__(self, llm:BaseChatModel):
        super().__init__()
        self._llm = llm

    #agent执行完后执行该方法。这是同步方法
    def after_agent(self, state: Dict[str,Any], runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """Logic to run after the agent execution completes.

        Args:
            state: The current agent state.
            runtime: The runtime context.

        Returns:
            Agent state updates to apply after agent execution.
        """

    # agent执行完后执行该方法。这是异步方法
    async def aafter_agent(
            self, state:  Dict[str,Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        """Async logic to run after the agent execution completes.

        Args:
            state: The current agent state.
            runtime: The runtime context.

        Returns:
            Agent state updates to apply after agent execution.
        """

        #上下文
        context=getattr(runtime,"context")

        if not context:
            return None

        user_id = getattr(runtime, "user_id")

        if not user_id:
            return None


        #获取消息列表
        messages=state.get("messages")
        if not messages:
            return None
        #获取和erp交互的最近一次有效消息
        message=self.__get_latest_interaction_message_with_erp(messages)
        if not message:
            return None


        #获取最近一次ai消息的摘要
        summary=self.__extract_message_summary(messages)


        #大模型提取采购相关的实体
        entity=self.__extract_purchase_entity_by_llm()

        if not entity:
            return None


        #获取store
        store=getattr(runtime,"store",None)
        if not store:
            return None

        namespace = (user_id,)
        key = f"/{user_id}/preferences.md"

        try:
            store_value=await store.aget(namespace,key)
        except:
            store_value=None

        if store_value is None or not hasattr(store_value,"value"):
            return None
        value=store_value.value

        if isinstance(value,dict):
            content=value.get("content", [])
            if isinstance(content,list):
                content_list=[str(line) for line in content]
            elif isinstance(content,str):
                content_list= content.split("\n")
        elif isinstance(value,str):
            content_list= value.split("\n")


        #合并兴趣爱好
        renew_content=self.__merge_preferences(content_list,entity.get("suppliers"),entity.get("query"))

        #获取存储文件的value值，并重新存储

        await store.aput(namespace, key, self.__get_file_value(renew_content))

        return None



    #和erp是否有有意义的交互
    def __get_latest_interaction_message_with_erp(self,messages):

        last_user_message=None

        #从最近一次与erp的交互记录
        for message in reversed(messages):

            #消息类型
            type= getattr(message,"type",None)
            if type=="human" :
                last_user_message=message
                break

        if last_user_message is None:
            return None



        message_content=last_user_message.content


        if isinstance(message_content,list):

            message_content=" ".join(
                part.get("text", "")
                if isinstance(part,dict) else str(part) for part in message_content
            )
        #把前后空格切掉
        message_content = str(message_content).strip()
        if not message_content:
            return None


        #过滤掉无意义的消息
        new_message_content=message_content.lower().replace(" ","")

        for word in _FILTER_WORDS:
            if word.lower().replace(" ", "") in new_message_content:
                return word


        #是否包含关键字
        for keyword in _FILTER_WORDS:
            if keyword.lower().replace(" ", "") in new_message_content:
                return message_content


        #是否子agent完成了任务
        for message in messages:
            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.get("name")=="task":
                        return message_content

        return None


    ##获取ai最近一条消息的摘要
    def __extract_message_summary(self,messages:list[BaseMessage])->str:

        for message in messages:
            if getattr(message,"type",None) == "ai":
                content=message.content
                if isinstance(content,list):
                    content=" ".join(
                        part.get("text") if isinstance(part,dict) else str(part)
                        for part in content
                    )

                return content

        return None

    ##根据模板，通过大模型提取采购相关实体
    async def __extract_purchase_entity_by_llm(self)->dict[str, Any] | None:
        system_prompt="""Extract procurement-related entities from this conversation.
        Rules:
        1. "suppliers": Company/supplier names mentioned. Include both Chinese and English names. Empty list if none.
        2. "query": One-line summary of the user's procurement need. Empty string if not procurement-related.
        
        User message: {user_message}
        
        Assistant response summary: {ai_summary}
        
        Return ONLY a JSON object, no other text:
        {{"suppliers": ["CompanyA", "CompanyB"], "query": "brief summary"}}
        """

        try:
            response= await llm.invoke(system_prompt)

            #从回复中提取
            content=response.content
            if isinstance(content,list):
                content=" ".join(
                    part.get("text","") if isinstance(part,dict) else str(part) for part in content
                )

            content=str(content).strip()

            start_index=content.find("{")
            end_index=content.find("}")
            if start_index>-1 and end_index>0 and end_index>start_index:
                result=json.loads(content[start_index:end_index+1])
                return {
                            "suppliers": result.get("suppliers", []),
                            "query": result.get("query", ""),
                        }

        except:
            pass

        return None



    ##合并兴趣爱好
    def __merge_preferences(self,content_list:list[str],suppliers:list[str],query:str)->None:



        def parse_content_list_inner(content_list:list[str],start_index:Number):

            line=content_list[start_index].strip()
            pos=line.find(":")
            if pos!=-1:
                sub_line=line[pos+1:].strip()
                if sub_line.startswith("[") and sub_line.endswith("]"):
                    #保留中括号中间的数据
                    goal_line=sub_line[1:-1].strip()
                    if goal_line:
                        return  [s.strip().strip("'").strip('"') for s in goal_line.split(",") if s.strip()], 1


            count=1
            result:list[str]=[]
            for i in range (start_index+1,len(content_list)):
                line=content_list[i].strip()
                if line.startswith("- "):

                    result.append(line[2:].strip().strip("'").strip('""'))
                    count+=1
                elif line and not content_list[i].startswith(" "):
                    break
                else:
                    count+=1
            return result, count

        supply_start_index = -1
        supply_len = 0
        query_start_index = -1
        query_len = 0
        existing_suppliers: list[str] = []
        existing_queries: list[str] = []
        for i,line in enumerate(content_list):
            line_str=line.strip()

            if line_str.startswith("recent_suppliers:"):
                #最近供应商
                supply_start_index=i
                existing_suppliers, supply_len=parse_content_list_inner(content_list,supply_start_index)
            elif  line_str.startswith("recent_queries"):
                query_start_index = i
                existing_queries, query_len = parse_content_list_inner(content_list, i)

        # 按起始位置降序排列，从后往前删除
        removals = []
        if supply_start_index >= 0:
            removals.append((supply_start_index, supply_len))
        if query_start_index >= 0:
            removals.append((query_start_index, query_len))
        removals.sort(key=lambda x: x[0], reverse=True)

        clean_lines = list(content_list)
        for start, length in removals:
            del clean_lines[start:start + length]

        # 4. 合并新值和旧值
        merged_suppliers = list(suppliers)
        for s in existing_suppliers:
            if s not in merged_suppliers:
                merged_suppliers.append(s)
        merged_suppliers = merged_suppliers[:10]

        merged_queries = [query] if query else []
        for q in existing_queries:
            if q.strip() not in [m.strip() for m in merged_queries]:
                merged_queries.append(q)
        merged_queries = merged_queries[:5]

        # 5. 追加合并后的区块
        result_lines = list(clean_lines)

        # 确保末尾有空行分隔
        if result_lines and result_lines[-1].strip():
            result_lines.append("")

        result_lines.append("recent_suppliers:")
        if merged_suppliers:
            for s in merged_suppliers:
                result_lines.append(f"  - {s}")
        else:
            result_lines[-1] = "recent_suppliers: []"

        result_lines.append("recent_queries:")
        if merged_queries:
            for q in merged_queries:
                result_lines.append(f"  - {q}")
        else:
            result_lines[-1] = "recent_queries: []"

        return "\n".join(result_lines).strip() + "\n"




    def __get_file_value(renew_content:str)->str:

        content_list = renew_content.split("\n")
        now = datetime.now(timezone.utc).isoformat()
        return {
            "content": content_list,
            "created_at": now,
            "modified_at": now,
        }






















































