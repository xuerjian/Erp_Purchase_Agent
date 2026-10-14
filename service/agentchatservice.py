import json
import os
from datetime import datetime

from langchain_protocol import Command
from opentelemetry.util import re

from bean.parambean import RequestBean
from agent import agentconfig
import uuid
from typing import AsyncIterable, Any, Dict
from agent.agentcreator import AgentCreator

from service.mongodbservice import MongoDBService

from agentconfig import mongo_client

class AgentChatService:



    async def agent_chat(self,request:RequestBean)-> AsyncIterable:

        #后期 增加鉴权，获取当前登录的用户信息
        content={"user_id":"xej","user_name":"xuerjian"}

        config=agentconfig.get_config(request.thread_id,content["user_id"])

        collect_content=""

        tool_stack = []

        if request.resume_data is not None:
            # 获取历史会话记录
            response_messages = await MongoDBService().get_history_messages_in_current_session(request.thread_id) or []

            input_message = Command(resume=request.resume_data)
        else:
            input_message={"messages":{"role":"user","content":request.input}}

            response_messages=[{
                "id":uuid.uuid4(),
                "content":request.input,
                "role":"user",
            }]




            async for chunk in AgentCreator.deep_agent.astream(
                    input=input_message,
                    config=config,
                    context=content,
                    stream_mode=["messages", "values"],
                    subgraphs=True,
                    version="v2",
            ):
                chunk_type = chunk.get("type")
                if chunk_type == "values" and chunk.get("interrupts"):
                    interrupts = chunk["interrupts"]

                    for interrupt in interrupts:
                        interrupt_value = interrupt.value

                        if "action_requests" in interrupt_value:
                           yield self.__get_sse_message({
                            "type": "interrupt",
                            "interrupt_type": "hitl_approval",
                            "action_requests": interrupt_value["action_requests"],
                            "review_configs": interrupt_value.get("review_configs", []),
                            "thread_id": request.thread_id,
                            })
                        elif  interrupt_value.get("type") == "order_info_request":
                            yield self.__get_sse_message({
                                "type": "interrupt",
                                "interrupt_type": "order_info_supplement",
                                "missing_fields": interrupt_value["missing_fields"],
                                "collected_data": interrupt_value["collected_data"],
                                "thread_id": request.thread_id,
                            })

                        else:
                            yield self.__get_sse_message({
                                "type": "interrupt",
                                "interrupt_type": "unknown",
                                "interrupt_value": str(interrupt_value)[:2000],
                                "thread_id": request.thread_id,
                            })
                    for message in response_messages:
                        if message["role"] == "tool" and message["tool_status"] == "calling":
                            message["tool_status"] = "done"

                    # 清理空的 assistant 消息
                    messages = [
                        dm for dm in response_messages
                        if not (dm["role"] == "assistant" and not dm.get("content"))
                    ]

                    await MongoDBService().save_display_messages(request.thread_id, messages)

                    yield self.__get_sse_message({
                        "type": "done",
                        "thread_id": request.thread_id,
                        "content": collect_content,
                        "interrupted": True,
                    })
                    return  # ← 结束本次流，等待前端 POST /resume

                if chunk_type!="messages":
                    continue

                token,meta=chunk["data"]
                ns=chunk.get("ns",())
                source="main"
                for s in ns:
                    if s.startswith("tools:"):
                        source= s.replace("tools:", "")
                        break


                if hasattr(token,"tool_call_chunks") and token.tool_call_chunks:
                    for chunk in token.tool_call_chunks:

                        if chunk.get("name") :
                            id=str(uuid.uuid4())
                            tool = {
                                "id": id,
                                "name": chunk['name'],
                                "args": "",
                                "source": source
                            }

                            tool_stack.append(tool)

                            yield self.__get_sse_message({
                                "type": "tool_start",
                                "tool_call_id": id,
                                "tool_name": chunk['name'],
                                "source": source
                            })

                            response_messages.append({
                                "id":id,
                                "role":"tool",
                                "tool_name":chunk["name"],
                                "args":"",
                                "text":"",
                                "images":[],
                                "source":source,
                                "tool_status":"calling"
                            })

                        if chunk.get('args'):
                            args = chunk['args']
                            if tool_stack:
                                tool_stack[-1]["args"]+=args

                            yield self.__get_sse_message({
                                "type": "tool_args",
                                "args": args,
                                "source": source
                            })


                            for message in reversed(response_messages):
                                if message["role"] == "tool" and message["tool_status"] == "calling":
                                    message["args"] += args
                                    break


                if hasattr(token,"type") and token.type=="tool":
                    tool_name=getattr(token,"name","工具未知")
                    content=getattr(token,"content","")


                    serialized=self.__serialize_tool_content(content)

                    finish_tool = tool_stack.pop() if tool_stack else None
                    id = finish_tool["id"] if finish_tool else ""

                    yield self.__get_sse_message({
                        "type": "tool_result",
                        "tool_name": tool_name,
                        "tool_call_id": id,
                        "text": serialized["text"],
                        "images": serialized["images"],
                        "source": source
                    })

                    # 更新展示消息中对应工具的结果
                    for message in reversed(response_messages):
                        if message["role"] == "tool" and message["id"] == id:
                            message["text"] = serialized["text"]
                            message["images"] = serialized["images"]
                            message["tool_status"] = "done"
                            break

                    yield self.__get_sse_message({
                        "type": "tool_end",
                        "tool_name": tool_name,
                        "tool_call_id": id,
                        "source": source
                    })

                    for message in reversed(response_messages):
                        if message["role"] == "tool" and message["id"] == id:
                            message["tool_status"] = "done"
                            break


                content=self.__extract_content_by_token(token)
                has_tool_calls = hasattr(token, 'tool_call_chunks') and token.tool_call_chunks
                is_tool_result = hasattr(token, 'type') and token.type == "tool"

                if content and not has_tool_calls and not is_tool_result:

                    collect_content +=content

                    yield self.__get_sse_message({
                        "type": "token",
                        "content": content,
                        "source": source
                    })

                    if response_messages and response_messages[-1]["role"] == "assistant":
                        response_messages[-1]["content"] += content
                        response_messages[-1]["source"] = source
                    else:
                        response_messages.append({
                            "id": f"assistant-{uuid.uuid4()}",
                            "role": "assistant",
                            "content": content,
                            "source": source
                        })


            for message in response_messages:
                if message["role"] == "tool" and message["tool_status"] == "calling":
                    message["tool_status"] = "done"

            # 清理空的 assistant 消息
            response_messages = [
                message for message in response_messages
                if not (message["role"] == "assistant" and not message.get("content"))
            ]

            if request.resume_data is None:
                history_messages= await MongoDBService().get_history_messages_in_current_session(request.thread_id) or []
                messages=history_messages+response_messages

            else:
                messages=response_messages

            #保存会话信息
            await MongoDBService().save_display_messages(request.thread_id,messages)

            yield self.__get_sse_message({
                "type": "done",
                "thread_id": request.thread_id,
                "content": collect_content
            })








    def __get_sse_message(self,data:dict)-> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"



    def __serialize_tool_content(self,content:str)->dict:

        result=dict[str,Any]={}

        if isinstance(content,str):
            result["text"]=content

            for match in re.finditer(r"\{(.*?)\}",content):
                url=match.group(1)
                if url not in result["images"]:
                     result["images"].append(url)
        elif isinstance(content,list):
            text_parts = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    item_type = item.get("type", "")
                    if item_type == "text":
                        t = item.get("text", "")
                        text_parts.append(t)
                    elif item_type == "image_url":
                        image_url = item.get("image_url", {})
                        url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
                        if url:
                            result["images"].append(url)
                    elif item_type == "image":
                        image_data = item.get("data", "") or item.get("image_data", "")
                        if image_data:
                            result["images"].append(image_data)
                    elif "text" in item:
                        text_parts.append(item["text"])
                    elif "content" in item:
                        text_parts.append(str(item["content"]))
                    else:
                        text_parts.append(str(item))
                else:
                    text_parts.append(str(item))
            result["text"] = ''.join(text_parts)
        else:
            result["text"] = str(content) if content is not None else ""


        if result["text"]:
            for match in re.finditer(r'!\[.*?\]\((.*?)\)',result["text"]):
                url=match.group(1)
                if url not in result["images"]:
                    result["images"].append(url)

            for match in re.finditer(r'data:image/[^;]+;base64,[A-Za-z0-9+/=]+', result["text"]):
                url = match.group(0)
                if url not in result["images"]:
                    result["images"].append(url)


        return result


    #在token中提取content内容
    def __extract_content_by_token(self,token:str)->str:

        if not hasattr(token, 'content'):
            return ""

        content = token.content

        if isinstance(content,str):
            if self.__is_likely_uuid(content):
                return ""
            return content

        if isinstance(content,list):
            content_list=[]
            for item in content:
                if isinstance(item,str):
                    content_list.append(item)
                elif isinstance(item,dict):
                    type = item.get("type", "")
                    if type == "text":
                        text = item.get("text", "")
                        if not self.__is_likely_uuid(text):
                            content_list.append(text)
                    elif "text" in item:
                        text = item["text"]
                        if not self.__is_likely_uuid(text):
                            content_list.append(text)
                    elif "content" in item:
                        content_list.append(str(item["content"]))

                else:
                    content_list.append(str(item))

            return ''.join(content_list)

        return str(content) if content is not None else ""




    def __is_likely_uuid(self,text: str) -> bool:
        """
        判断文本是否大概率是 UUID（而非有意义的回复内容）
        例如：3576bba4-42e5-a769-c2f7-ea8444829951
        """
        # UUID 格式：8-4-4-4-12
        uuid_pattern = r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        return bool(re.match(uuid_pattern, text.strip()))



    async def get_current_messages(self, thread_id: str) -> list[Dict[str, Any]]:
        """
        获取当前会话的消息列表

        Args:
            thread_id: 会话 ID

        Returns:
            List[Dict]: 消息列表
        """
        config=agentconfig.get_config(thread_id)

        try:
            state = await  AgentCreator.deep_agent.aget_state(config)
            if state and state.values:
                return state.values.get("messages", [])
        except Exception as e:
            print(f"[AgentLoader] 获取消息失败: {e}")

        return []




    async def get_state_history(self,
        thread_id: str,
        limit: int = 50)->list[Any]:
        """
        获取会话的历史状态

        Args:
            thread_id: 会话 ID
            limit: 返回的最大状态数量

        Returns:
            List[StateSnapshot]: 状态快照列表
        """
        config=agentconfig.get_config(thread_id)
        states = []

        # 使用 agent.get_state_history 获取历史
        async for state in AgentCreator.deep_agent.aget_state_history(config):
            states.append(state)
            if len(states) >= limit:
                break

        return states


    def get_all_thread_ids(self) -> list[str]:
        """
        从 MongoDB 获取所有会话的 thread_id

        Returns:
            List[str]: 所有会话 ID 列表
        """
        if mongo_client is None:
            return []

        db = mongo_client[os.getenv("MGDB_DATABASE_NAME",default="context_db"),]
        collection = db[os.getenv("MGDB_CHECKPOINTER_COLLECTION",default="purchase_agent")]

        # 获取所有唯一的 thread_id（MongoDB 文档中 thread_id 直接存储在顶层字段）
        thread_ids = collection.distinct("thread_id")

        # 过滤掉空值和通配符
        return [tid for tid in thread_ids if tid and tid != "*" and tid != "" and tid is not None]


    def get_session_updated_at(self, thread_id: str) -> datetime:
        """
        获取会话的最后更新时间

        Args:
            thread_id: 会话 ID

        Returns:
            datetime: 最后更新时间
        """
        if mongo_client is None:
            return datetime.now()

        db = mongo_client[os.getenv("MGDB_DATABASE_NAME",default="context_db")]
        collection = db[os.getenv("MGDB_CHECKPOINTER_COLLECTION",default="purchase_agent")]

        try:
            # 获取该 thread_id 的最新文档（按 _id 倒序，_id 包含时间戳）
            latest_doc = collection.find_one(
                {"thread_id": thread_id},
                sort=[("_id", -1)]
            )

            if latest_doc:
                # 从 _id 中提取时间戳（MongoDB _id 的前4字节是时间戳）
                if "_id" in latest_doc and hasattr(latest_doc["_id"], 'generation_time'):
                    return latest_doc["_id"].generation_time
                # 如果没有 generation_time 属性，尝试其他方式
                elif "_id" in latest_doc:
                    import bson
                    if isinstance(latest_doc["_id"], bson.objectid.ObjectId):
                        return latest_doc["_id"].generation_time

            return datetime.now()
        except Exception as e:
            print(f"[AgentLoader] 获取会话时间失败: {e}")
            return datetime.now()


    async def delete_session(self, thread_id: str) -> bool:
        """
        删除会话（删除该 thread_id 下的所有 checkpoint）

        Args:
            thread_id: 会话 ID

        Returns:
            bool: 是否删除成功
        """
        if mongo_client is None:
            return False

        db = mongo_client[os.getenv("MGDB_DATABASE_NAME", default="context_db")]
        collection = db[os.getenv("MGDB_CHECKPOINTER_COLLECTION", default="purchase_agent")]

        try:
            # 删除该 thread_id 的所有 checkpoint
            result = collection.delete_many({
                "thread_id": thread_id
            })
            # 同步删除展示消息
            display_collection = db["session_display_messages"]
            display_result = display_collection.delete_many({"thread_id": thread_id})
            print(f"[AgentLoader] 已删除会话 {thread_id}，checkpoint {result.deleted_count} 条，展示消息 {display_result.deleted_count} 条")
            return True
        except Exception as e:
            print(f"[AgentLoader] 删除会话失败: {e}")
            return False