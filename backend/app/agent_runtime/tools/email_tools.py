import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .base import BaseTool, ToolSpec, ToolResult


class SendEmailTool(BaseTool):
    name = "send_email"
    description = "Send an email. Uses configured SMTP settings from environment variables (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM)."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Email body content (plain text)"}
                },
                "required": ["to", "subject", "body"]
            }
        )

    async def execute(self, to: str = "", subject: str = "", body: str = "", **kwargs) -> ToolResult:
        smtp_host = os.getenv("SMTP_HOST", "")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")
        smtp_from = os.getenv("SMTP_FROM", smtp_user)

        if not smtp_host:
            return ToolResult(success=False, error="SMTP not configured. Set SMTP_HOST environment variable.")

        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_from
            msg["To"] = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                if smtp_user:
                    server.login(smtp_user, smtp_password)
                server.send_message(msg)

            return ToolResult(success=True, data=f"Email sent to {to}: {subject}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
