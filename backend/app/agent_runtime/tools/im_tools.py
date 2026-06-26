"""
企业即时通讯工具（企业微信、飞书、QQ、微信）
支持通过 Webhook 或 API 发送消息
"""
import json
import httpx
from typing import Optional
from .base import BaseTool, ToolSpec, ToolResult


class WeChatWorkTool(BaseTool):
    """企业微信机器人工具"""
    name = "wechat_work_send"
    category = "im"
    description = (
        "Send message to WeChat Work (企业微信) group via webhook. "
        "You need to configure the webhook URL first in the employee's integration settings."
    )
    timeout_seconds = 30

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Message content to send (plain text).",
                    },
                    "msgtype": {
                        "type": "string",
                        "description": "Message type: text (default), markdown, image, news.",
                        "default": "text",
                    },
                    "mentioned_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of user IDs to @mention (e.g., ['@all']).",
                    },
                },
                "required": ["content"],
            },
        )

    async def execute(
        self,
        content: str = "",
        msgtype: str = "text",
        mentioned_list: Optional[list] = None,
        webhook_url: str = "",
        **kwargs,
    ) -> ToolResult:
        if not content.strip():
            return ToolResult(success=False, error="content is required")
        
        if not webhook_url:
            return ToolResult(
                success=False,
                error="企业微信 Webhook 未配置。请先在该员工的集成设置中添加企业微信机器人 Webhook。"
            )

        try:
            payload = {"msgtype": msgtype}
            
            if msgtype == "text":
                payload["text"] = {
                    "content": content,
                    "mentioned_list": mentioned_list or [],
                }
            elif msgtype == "markdown":
                payload["markdown"] = {"content": content}
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                
                if result.get("errcode") == 0:
                    return ToolResult(
                        success=True,
                        data={
                            "message": "企业微信消息发送成功",
                            "msgtype": msgtype,
                            "content_length": len(content),
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"企业微信发送失败: {result.get('errmsg', str(result))}"
                    )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"发送企业微信消息时出错: {str(e)}"
            )


class FeishuTool(BaseTool):
    """飞书（Lark）机器人工具"""
    name = "feishu_send"
    category = "im"
    description = (
        "Send message to Feishu (飞书) group via webhook. "
        "You need to configure the webhook URL first in the employee's integration settings."
    )
    timeout_seconds = 30

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Message content to send (plain text or JSON for rich messages).",
                    },
                    "msg_type": {
                        "type": "string",
                        "description": "Message type: text (default), interactive, post, share_chat, image.",
                        "default": "text",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional title for card messages.",
                    },
                },
                "required": ["content"],
            },
        )

    async def execute(
        self,
        content: str = "",
        msg_type: str = "text",
        title: str = "",
        webhook_url: str = "",
        **kwargs,
    ) -> ToolResult:
        if not content.strip():
            return ToolResult(success=False, error="content is required")
        
        if not webhook_url:
            return ToolResult(
                success=False,
                error="飞书 Webhook 未配置。请先在该员工的集成设置中添加飞书机器人 Webhook。"
            )

        try:
            payload = {"msg_type": msg_type}
            
            if msg_type == "text":
                payload["content"] = {"text": content}
            elif msg_type == "post":
                payload["content"] = {
                    "post": {
                        "zh_cn": {
                            "title": title or "通知",
                            "content": [[{"tag": "text", "text": content}]],
                        }
                    }
                }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                
                if result.get("code") == 0:
                    return ToolResult(
                        success=True,
                        data={
                            "message": "飞书消息发送成功",
                            "msg_type": msg_type,
                            "content_length": len(content),
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"飞书发送失败: {result.get('msg', str(result))}"
                    )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"发送飞书消息时出错: {str(e)}"
            )


class QQBotTool(BaseTool):
    """QQ 机器人工具"""
    name = "qq_send"
    category = "im"
    description = (
        "Send message to QQ (via go-cqhttp or other QQ bot framework). "
        "Requires QQ bot API endpoint configuration."
    )
    timeout_seconds = 30

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message content to send.",
                    },
                    "target_type": {
                        "type": "string",
                        "description": "Target type: private (direct message), group (group message).",
                        "default": "group",
                    },
                    "target_id": {
                        "type": "string",
                        "description": "QQ number or group ID to send message to.",
                    },
                },
                "required": ["message", "target_id"],
            },
        )

    async def execute(
        self,
        message: str = "",
        target_type: str = "group",
        target_id: str = "",
        api_endpoint: str = "",
        access_token: str = "",
        **kwargs,
    ) -> ToolResult:
        if not message.strip():
            return ToolResult(success=False, error="message is required")
        if not target_id:
            return ToolResult(success=False, error="target_id is required")
        
        if not api_endpoint:
            return ToolResult(
                success=False,
                error="QQ Bot API 端点未配置。请先在该员工的集成设置中添加 QQ 机器人配置。"
            )

        try:
            endpoint = f"{api_endpoint.rstrip('/')}/send_msg"
            
            payload = {
                "message_type": target_type,
                "message": message,
            }
            
            if target_type == "group":
                payload["group_id"] = int(target_id)
            else:
                payload["user_id"] = int(target_id)
            
            headers = {"Content-Type": "application/json"}
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                )
                result = response.json()
                
                if result.get("retcode") == 0:
                    return ToolResult(
                        success=True,
                        data={
                            "message": "QQ 消息发送成功",
                            "target_type": target_type,
                            "message_id": result.get("data", {}).get("message_id"),
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"QQ 发送失败: {result.get('wording', str(result))}"
                    )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"发送 QQ 消息时出错: {str(e)}"
            )


class WeChatBotTool(BaseTool):
    """微信机器人工具（通过微信Hook或第三方API）"""
    name = "wechat_send"
    category = "im"
    description = (
        "Send message to WeChat (微信) via bot framework (e.g., WeChat Hook, ComWeChat). "
        "Requires WeChat bot API configuration."
    )
    timeout_seconds = 30

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Message content to send.",
                    },
                    "receiver": {
                        "type": "string",
                        "description": "WeChat ID or nickname to send to.",
                    },
                    "is_group": {
                        "type": "boolean",
                        "description": "Whether receiver is a group chat.",
                        "default": False,
                    },
                },
                "required": ["content", "receiver"],
            },
        )

    async def execute(
        self,
        content: str = "",
        receiver: str = "",
        is_group: bool = False,
        api_endpoint: str = "",
        **kwargs,
    ) -> ToolResult:
        if not content.strip():
            return ToolResult(success=False, error="content is required")
        if not receiver:
            return ToolResult(success=False, error="receiver is required")
        
        if not api_endpoint:
            return ToolResult(
                success=False,
                error="微信 Bot API 端点未配置。请先在该员工的集成设置中添加微信机器人配置。"
            )

        try:
            payload = {
                "type": "group" if is_group else "private",
                "to": receiver,
                "content": content,
            }
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    api_endpoint.rstrip("/") + "/send",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                result = response.json()
                
                if result.get("success") or result.get("code") == 200:
                    return ToolResult(
                        success=True,
                        data={
                            "message": "微信消息发送成功",
                            "receiver": receiver,
                            "is_group": is_group,
                        },
                    )
                else:
                    return ToolResult(
                        success=False,
                        error=f"微信发送失败: {result.get('message', str(result))}"
                    )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"发送微信消息时出错: {str(e)}"
            )
