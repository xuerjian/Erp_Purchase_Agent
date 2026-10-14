from fastapi import HTTPException,Query
from starlette.responses import StreamingResponse

from app import app
import uuid

from bean.parambean import RequestBean, Message, ChatResponse
from service.agentchatservice import AgentChatService
from datetime import datetime

agent_chat_service = AgentChatService()


@app.post("/stream")
async def agent_chat(request:RequestBean)->StreamingResponse:

    if request.thread_id is None:

        request.thread_id = str(uuid.uuid4())
    from starlette import status
    return StreamingResponse(
        content=agent_chat_service.agent_chat(request),
        status_code=status.HTTP_200_OK,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"}
    )


@app.post("/resume")
async def chat_resume( request: RequestBean):
    """
    中断恢复接口

    当中断发生后，前端收集用户决策/补充数据，通过此端点恢复 Agent 执行。
    request.resume 的格式取决于中断类型：
    - 数据补充: {"supplement": "用户输入的补充信息"}
    - HITL 审批: {"decisions": [{"type": "approve"}]} 或 [{"type": "reject"}]
    """
    return StreamingResponse(
        content=agent_chat_service.agent_chat(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/state/{thread_id}")
async def get_chat_state(thread_id: str):
    """获取会话状态"""
    try:
        messages = await agent_chat_service.get_current_messages(thread_id)

        message_list = []
        for i, msg in enumerate(messages):
            message = Message(
                id=f"msg-{i}",
                role=msg.get("role", "assistant"),
                content=msg.get("content", ""),
                created_at=datetime.now(),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
            )
            message_list.append(message)

        return ChatResponse(
            thread_id=thread_id,
            messages=message_list
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/{thread_id}/history")
async def get_chat_history(
    thread_id: str,
    limit: int = Query(50, ge=1, le=100)
):
    """获取会话历史状态列表"""
    try:
        states = await agent_chat_service.get_state_history(thread_id, limit)

        return {
            "thread_id": thread_id,
            "states": [
                {
                    "config": state.config,
                    "values": state.values,
                    "created_at": state.created_at,
                    "parent_config": state.parent_config
                }
                for state in states
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))













