import os
from pathlib import Path
from .base import BaseTool, ToolSpec, ToolResult


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file. Provide the file path relative to the workspace."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to read, relative to workspace root"}
                },
                "required": ["path"]
            }
        )

    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        full_path = Path(os.getcwd()) / path
        try:
            resolved = full_path.resolve()
            if not str(resolved).startswith(str(Path(os.getcwd()).resolve())):
                return ToolResult(success=False, error="Access denied: path traversal detected")
            if not resolved.exists():
                return ToolResult(success=False, error=f"File not found: {path}")
            content = resolved.read_text(encoding="utf-8")
            if len(content) > 50000:
                content = content[:50000] + "\n...[truncated]"
            return ToolResult(success=True, data=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file. Provide the file path and content."
    requires_approval = True

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to write"},
                    "content": {"type": "string", "description": "Content to write to the file"}
                },
                "required": ["path", "content"]
            }
        )

    async def execute(self, path: str = "", content: str = "", **kwargs) -> ToolResult:
        full_path = Path(os.getcwd()) / path
        try:
            resolved = full_path.resolve()
            if not str(resolved).startswith(str(Path(os.getcwd()).resolve())):
                return ToolResult(success=False, error="Access denied")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(success=True, data=f"File written: {path} ({len(content)} bytes)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List files and directories at the given path."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list"}
                },
                "required": ["path"]
            }
        )

    async def execute(self, path: str = ".", **kwargs) -> ToolResult:
        full_path = Path(os.getcwd()) / path
        try:
            resolved = full_path.resolve()
            if not str(resolved).startswith(str(Path(os.getcwd()).resolve())):
                return ToolResult(success=False, error="Access denied")
            if not resolved.is_dir():
                return ToolResult(success=False, error=f"Not a directory: {path}")
            items = []
            for item in sorted(resolved.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                size = ""
                if item.is_file():
                    s = item.stat().st_size
                    if s < 1024:
                        size = f" ({s}B)"
                    elif s < 1024 * 1024:
                        size = f" ({s/1024:.1f}KB)"
                    else:
                        size = f" ({s/1024/1024:.1f}MB)"
                items.append(f"{prefix}{item.name}{size}")
            return ToolResult(success=True, data="\n".join(items) if items else "(empty directory)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
