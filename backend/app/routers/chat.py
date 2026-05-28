import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import ensure_agent_access, get_current_user
from ..database import get_db, async_session
from ..models import Message, Task, UserAccount
from ..schemas import ChatRequest, ConversationRenameRequest
from ..services import build_execution_output, build_org_context, get_agent, get_conversation, create_conversation, get_conversation_messages, get_tools_for_agent, get_enterprise_llm_key
from ..agent_runtime.core import AgentRuntime, AgentConfig, AgentEvent
from ..time_utils import now_beijing

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event_type: str, content: str, data: dict | None = None) -> str:
    payload = {"content": content, "data": data or {}}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/{agent_id}")
async def chat_with_agent(
    agent_id: str,
    data: ChatRequest,
    current_user: UserAccount = Depends(get_current_user),
):
    """Stream chat response via SSE (Server-Sent Events)."""
    ensure_agent_access(current_user, agent_id)

    async def stream():
        async with async_session() as db:
            agent = await get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
            if not agent:
                yield _sse("error", "Agent not found")
                return

            conv = None
            if data.save_conversation and data.conversation_id:
                conv = await get_conversation(db, data.conversation_id, agent_id=agent_id)
                if not conv:
                    yield _sse("error", "Conversation not found")
                    return
            elif data.save_conversation:
                conv = await create_conversation(db, agent_id)

            history = await get_conversation_messages(db, conv_id=conv.id) if conv else []

            if conv:
                user_msg = Message(conversation_id=conv.id, role="user", content=data.message)
                db.add(user_msg)
            agent.status = "working"
            agent.current_task = data.message[:200]
            agent.updated_at = now_beijing()
            await db.commit()

            tools = get_tools_for_agent(agent)
            org_context = await build_org_context(db, agent)
            config = AgentConfig(
                system_prompt=f"{agent.system_prompt}\n\n{org_context}",
                max_iterations=agent.max_iterations,
                provider=agent.provider,
                model_name=agent.model_name,
                tools=tools,
                agent_id=agent.id,
                api_key=await get_enterprise_llm_key(db, agent.enterprise_id, agent.provider),
            )
            try:
                runtime = AgentRuntime(config)
            except Exception as e:
                agent.status = "blocked"
                agent.current_task = None
                agent.updated_at = now_beijing()
                await db.commit()
                yield _sse("error", f"Agent 初始化失败: {str(e)}")
                return

            full_response = ""
            final_data = {}
            had_error = False
            finalized = False

            async def finalize(interrupted: bool = False):
                nonlocal finalized, full_response
                if finalized:
                    return
                finalized = True

                if interrupted and not full_response.strip() and not final_data.get("tool_calls"):
                    full_response = "本次执行被中断，尚未产生可保存的文本结果。"

                # Auto-title: use first user message truncated to 30 chars
                if conv and conv.title == "新对话":
                    conv.title = data.message[:30] + ("..." if len(data.message) > 30 else "")

                agent.status = "blocked" if had_error else "idle"
                agent.current_task = None
                agent.updated_at = now_beijing()
                final_output = build_execution_output(full_response, final_data)
                if interrupted and not final_output.startswith("本次执行被中断"):
                    final_output = f"本次执行被中断，以下是已保存的部分结果：\n{final_output}"

                if conv:
                    assistant_msg = Message(
                        conversation_id=conv.id,
                        role="assistant",
                        content=final_output,
                        token_count=final_data.get("tokens", 0),
                    )
                    db.add(assistant_msg)
                    conv.updated_at = now_beijing()
                await db.commit()

            try:
                async for event in runtime.run_stream(data.message, history):
                    if event.type == "text_delta":
                        full_response += event.content
                    elif event.type == "tool_cycle":
                        tool_calls_stored = []
                        for tc in event.data.get("tool_calls", []):
                            tool_calls_stored.append({
                                "id": tc["id"],
                                "name": tc["name"],
                                "input": tc["input"],
                            })

                        if tool_calls_stored and conv:
                            assistant_tool_msg = Message(
                                conversation_id=conv.id,
                                role="assistant",
                                content=event.data.get("assistant_content") or None,
                                tool_calls=tool_calls_stored,
                            )
                            db.add(assistant_tool_msg)

                        if conv:
                            for tc in event.data.get("tool_calls", []):
                                tool_msg = Message(
                                    conversation_id=conv.id,
                                    role="tool",
                                    content=tc.get("output", ""),
                                    tool_call_id=tc["id"],
                                )
                                db.add(tool_msg)
                            await db.commit()
                        full_response = ""
                    elif event.type == "done":
                        final_data = event.data
                        if conv:
                            final_data["conversation_id"] = conv.id
                    elif event.type == "error":
                        yield _sse("error", event.content)
                        full_response = f"错误: {event.content}"
                        had_error = True
                        break

                    yield _sse(event.type, event.content, event.data)
            except BaseException:
                await finalize(interrupted=True)
                raise
            else:
                await finalize(interrupted=False)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/conversations/{conv_id}/rename")
async def rename_conversation(
    conv_id: str,
    data: ConversationRenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    conv = await get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    agent = await get_agent(db, conv.agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(404, "Conversation not found")
    ensure_agent_access(current_user, conv.agent_id)
    title = data.title.strip()
    if not title:
        raise HTTPException(422, "Conversation title cannot be empty")
    conv.title = title
    conv.updated_at = now_beijing()
    await db.commit()
    return {"ok": True}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    conv = await get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    agent = await get_agent(db, conv.agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(404, "Conversation not found")
    ensure_agent_access(current_user, conv.agent_id)

    await db.execute(
        update(Task)
        .where(Task.conversation_id == conv_id)
        .values(conversation_id=None)
    )
    await db.delete(conv)
    await db.commit()
    return {"ok": True}


@router.get("/conversations/{agent_id}")
async def list_conversations(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    ensure_agent_access(current_user, agent_id)
    agent = await get_agent(db, agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    from sqlalchemy import select
    from ..models import Conversation
    result = await db.execute(
        select(Conversation)
        .where(Conversation.agent_id == agent_id)
        .order_by(Conversation.updated_at.desc())
        .limit(20)
    )
    convs = result.scalars().all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in convs
    ]


@router.get("/messages/{conv_id}")
async def get_messages(
    conv_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserAccount = Depends(get_current_user),
):
    """Load all messages for a conversation, in chat display format."""
    from sqlalchemy import select
    conv = await get_conversation(db, conv_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    agent = await get_agent(db, conv.agent_id, enterprise_id=current_user.enterprise_id)
    if not agent:
        raise HTTPException(404, "Conversation not found")
    ensure_agent_access(current_user, conv.agent_id)
    result = await db.execute(
        select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)
    )
    msgs = result.scalars().all()
    out = []
    for m in msgs:
        item: dict = {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "tool_call_id": m.tool_call_id,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        if m.tool_calls:
            item["tool_calls"] = m.tool_calls
        out.append(item)
    return out
