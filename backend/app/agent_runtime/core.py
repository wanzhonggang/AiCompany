import asyncio
import json
import logging
from typing import AsyncIterator, Optional
from dataclasses import dataclass, field

from openai import AsyncOpenAI

from ..config import settings, get_provider
from .tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    system_prompt: str = "You are a helpful AI assistant."
    max_iterations: int = 25
    provider: str = "deepseek"
    model_name: str = "deepseek-chat"
    tools: list[BaseTool] = field(default_factory=list)


@dataclass
class AgentEvent:
    type: str  # "text_delta", "tool_use", "tool_result", "thinking", "done", "error"
    content: str = ""
    data: dict = field(default_factory=dict)


class AgentRuntime:
    """Core ReAct loop using OpenAI-compatible API (DeepSeek)."""

    def __init__(self, config: AgentConfig):
        self.config = config
        provider = get_provider(config.provider)
        if not provider:
            raise ValueError(f"Unknown LLM provider: {config.provider}")
        if not provider.get("api_key"):
            raise ValueError(
                f"Missing API key for provider: {config.provider}. "
                f"Set {provider.get('api_key_env') or config.provider.upper() + '_API_KEY'} in backend/.env."
            )
        self.client = AsyncOpenAI(
            api_key=provider["api_key"],
            base_url=provider["base_url"],
        )

    def _build_tools(self) -> list[dict] | None:
        if not self.config.tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.get_spec().input_schema,
                },
            }
            for tool in self.config.tools
        ]

    def _find_tool(self, name: str) -> Optional[BaseTool]:
        for tool in self.config.tools:
            if tool.name == name:
                return tool
        return None

    async def run_stream(
        self,
        user_message: str,
        history: list[dict] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        messages: list[dict] = []

        # System prompt
        messages.append({"role": "system", "content": self.config.system_prompt})

        # Conversation history (OpenAI format)
        if history:
            messages.extend(history)

        # Current user message
        messages.append({"role": "user", "content": user_message})

        yield AgentEvent(type="thinking", content="开始分析任务...")

        tools = self._build_tools()
        iteration = 0
        total_tokens = 0
        all_tool_calls_for_event: list[dict] = []

        while iteration < self.config.max_iterations:
            iteration += 1
            logger.info(f"Agent iteration {iteration}/{self.config.max_iterations}")

            # ── Step 1: Call LLM with streaming ──
            try:
                stream = await self.client.chat.completions.create(
                    model=self.config.model_name,
                    messages=messages,
                    tools=tools,
                    stream=True,
                )
            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                yield AgentEvent(type="error", content=f"AI 调用失败: {str(e)}")
                break

            content = ""
            tool_calls: list[dict] = []

            async for chunk in stream:
                if chunk.usage:
                    total_tokens += chunk.usage.total_tokens

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    content += delta.content
                    yield AgentEvent(type="text_delta", content=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "function": {"name": "", "arguments": ""}})

                        if tc_delta.id:
                            tool_calls[idx]["id"] = tc_delta.id

                        if tc_delta.function:
                            if tc_delta.function.name:
                                tool_calls[idx]["function"]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments

            # ── No tool calls → task complete ──
            if not tool_calls:
                messages.append({"role": "assistant", "content": content})
                yield AgentEvent(
                    type="done",
                    content="任务完成",
                    data={
                        "iterations": iteration,
                        "tokens": total_tokens,
                        "tool_calls": all_tool_calls_for_event,
                    },
                )
                break

            # ── Emit tool_use events with complete data ──
            for tc in tool_calls:
                yield AgentEvent(
                    type="tool_use",
                    content=f"调用工具: {tc['function']['name']}",
                    data={"tool_name": tc["function"]["name"], "tool_id": tc["id"]},
                )

            # ── Build assistant message with tool calls ──
            serialized_calls = []
            for tc in tool_calls:
                serialized_calls.append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                })

            assistant_msg: dict = {
                "role": "assistant",
                "content": content or None,
            }
            if serialized_calls:
                assistant_msg["tool_calls"] = serialized_calls
            messages.append(assistant_msg)

            # ── Step 2: Execute tools ──
            tool_results_for_event = []
            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool = self._find_tool(tool_name)

                if not tool:
                    result = ToolResult(success=False, error=f"Unknown tool: {tool_name}")
                    yield AgentEvent(
                        type="tool_result",
                        content=f"未知工具: {tool_name}",
                        data={"tool_name": tool_name, "error": True},
                    )
                else:
                    yield AgentEvent(
                        type="tool_result",
                        content=f"执行 {tool_name}...",
                        data={"tool_name": tool_name, "running": True},
                    )

                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, TypeError):
                        args = {}

                    try:
                        result = await asyncio.wait_for(
                            tool.execute(**args),
                            timeout=tool.timeout_seconds,
                        )
                    except asyncio.TimeoutError:
                        result = ToolResult(success=False, error=f"Tool timed out after {tool.timeout_seconds}s")
                    except Exception as e:
                        result = ToolResult(success=False, error=str(e))

                    yield AgentEvent(
                        type="tool_result",
                        content=result.to_llm_format()[:500],
                        data={"tool_name": tool_name, "success": result.success},
                    )

                # Add tool result to conversation
                result_text = result.to_llm_format()
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result_text,
                })

                # Record for the done event
                try:
                    args_dict = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    args_dict = {}
                tool_results_for_event.append({
                    "id": tc["id"],
                    "name": tool_name,
                    "input": args_dict,
                    "success": result.success,
                    "output": result_text[:1000],
                })

            all_tool_calls_for_event.extend(tool_results_for_event)
            yield AgentEvent(
                type="tool_cycle",
                content="工具执行完成",
                data={
                    "iterations": iteration,
                    "tokens": total_tokens,
                    "assistant_content": content,
                    "tool_calls": tool_results_for_event,
                },
            )
            continue

        else:
            # Max iterations reached
            yield AgentEvent(
                type="done",
                content=f"达到最大迭代次数 ({self.config.max_iterations})，已停止。",
                data={
                    "iterations": iteration,
                    "tokens": total_tokens,
                    "max_reached": True,
                    "tool_calls": all_tool_calls_for_event,
                },
            )

    async def run(
        self,
        user_message: str,
        history: list[dict] | None = None,
    ) -> dict:
        """Non-streaming version. Returns final result."""
        final_text = ""
        final_data = {}
        async for event in self.run_stream(user_message, history):
            if event.type == "text_delta":
                final_text += event.content
            elif event.type == "done":
                final_data = event.data
            elif event.type == "error":
                final_data["error"] = event.content
        return {"text": final_text, "data": final_data}
