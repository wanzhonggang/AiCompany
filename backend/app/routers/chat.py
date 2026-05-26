import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db, async_session
from ..models import Message
from ..schemas import ChatRequest
from ..services import get_agent, get_conversation, create_conversation, get_conversation_messages, get_tools_for_agent
from ..agent_runtime.core import AgentRuntime, AgentConfig, AgentEvent

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(event_type: str, content: str, data: dict | None = None) -> str:
    payload = {"content": content, "data": data or {}}
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/{agent_id}")
async def chat_with_agent(agent_id: str, data: ChatRequest):
    """Stream chat response via SSE (Server-Sent Events)."""

    async def stream():
        async with async_session() as db:
            agent = await get_agent(db, agent_id)
            if not agent:
                yield _sse("error", "Agent not found")
                return

            if data.conversation_id:
                conv = await get_conversation(db, data.conversation_id)
                if not conv:
                    yield _sse("error", "Conversation not found")
                    return
            else:
                conv = await create_conversation(db, agent_id)

            history = await get_conversation_messages(db, conv_id=conv.id)

            user_msg = Message(conversation_id=conv.id, role="user", content=data.message)
            db.add(user_msg)
            await db.commit()

            tools = get_tools_for_agent(agent)
            config = AgentConfig(
                system_prompt=agent.system_prompt,
                max_iterations=agent.max_iterations,
                provider=agent.provider,
                model_name=agent.model_name,
                tools=tools,
            )
            runtime = AgentRuntime(config)

            full_response = ""
            tool_calls_stored = []
            final_data = {}

            async for event in runtime.run_stream(data.message, history):
                if event.type == "text_delta":
                    full_response += event.content
                elif event.type == "done":
                    final_data = event.data
                    for tc in event.data.get("tool_calls", []):
                        tool_calls_stored.append({
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc["input"],
                        })
                        tool_msg = Message(
                            conversation_id=conv.id,
                            role="tool",
                            content=tc.get("output", ""),
                            tool_call_id=tc["id"],
                        )
                        db.add(tool_msg)
                elif event.type == "error":
                    yield _sse("error", event.content)
                    full_response = f"错误: {event.content}"
                    break

                yield _sse(event.type, event.content, event.data)

            agent.status = "idle"
            agent.current_task = None
            agent.updated_at = datetime.utcnow()

            assistant_msg = Message(
                conversation_id=conv.id,
                role="assistant",
                content=full_response,
                tool_calls=tool_calls_stored if tool_calls_stored else None,
                token_count=final_data.get("tokens", 0),
            )
            db.add(assistant_msg)
            conv.updated_at = datetime.utcnow()
            await db.commit()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations/{agent_id}")
async def list_conversations(agent_id: str, db: AsyncSession = Depends(get_db)):
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
        {"id": c.id, "title": c.title, "status": c.status, "created_at": c.created_at.isoformat()}
        for c in convs
    ]
