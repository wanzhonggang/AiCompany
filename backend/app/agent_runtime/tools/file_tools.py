import os
from pathlib import Path
from .base import BaseTool, ToolSpec, ToolResult


def _workspace_root() -> Path:
    cwd = Path(os.getcwd()).resolve()
    return cwd.parent if cwd.name.lower() == "backend" else cwd


def _desktop_root() -> Path:
    return (Path.home() / "Desktop").resolve()


def _allowed_roots() -> list[Path]:
    roots = [_workspace_root(), Path(os.getcwd()).resolve()]
    desktop = _desktop_root()
    if desktop.exists():
        roots.append(desktop)
    return list(dict.fromkeys(roots))


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_user_path(path: str) -> tuple[Path | None, str | None]:
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        raw = "."

    lowered = raw.lower()
    desktop_aliases = ("desktop", "desktop/", "桌面", "桌面/")
    if lowered == "desktop" or lowered.startswith("desktop/") or raw == "桌面" or raw.startswith("桌面/"):
        _, _, rest = raw.partition("/")
        candidate = _desktop_root() / rest
    elif raw.startswith("~/Desktop/") or raw == "~/Desktop":
        candidate = _desktop_root() / raw[len("~/Desktop"):].lstrip("/")
    else:
        input_path = Path(raw)
        candidate = input_path if input_path.is_absolute() else _workspace_root() / input_path

    resolved = candidate.resolve()
    if any(_is_under(resolved, root) for root in _allowed_roots()):
        return resolved, None
    return None, "Access denied: only the project workspace and your Desktop are available"


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read a file from the project workspace or Desktop. Desktop paths can be written as Desktop/name.txt or 桌面/name.txt."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to read. Use Desktop/name.txt or 桌面/name.txt for the user's Desktop."}
                },
                "required": ["path"]
            }
        )

    async def execute(self, path: str = "", **kwargs) -> ToolResult:
        try:
            resolved, error = _resolve_user_path(path)
            if error or resolved is None:
                return ToolResult(success=False, error=error or "Invalid path")
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
    description = "Write content to a file in the project workspace or Desktop. Desktop paths can be written as Desktop/name.txt or 桌面/name.txt."
    requires_approval = True

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to write. Use Desktop/name.txt or 桌面/name.txt for the user's Desktop."},
                    "content": {"type": "string", "description": "Content to write to the file"}
                },
                "required": ["path", "content"]
            }
        )

    async def execute(self, path: str = "", content: str = "", **kwargs) -> ToolResult:
        try:
            resolved, error = _resolve_user_path(path)
            if error or resolved is None:
                return ToolResult(success=False, error=error or "Invalid path")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
            return ToolResult(success=True, data=f"File written: {resolved} ({len(content)} bytes)")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List files and directories in the project workspace or Desktop."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to list. Use Desktop or 桌面 for the user's Desktop."}
                },
                "required": ["path"]
            }
        )

    async def execute(self, path: str = ".", **kwargs) -> ToolResult:
        try:
            resolved, error = _resolve_user_path(path)
            if error or resolved is None:
                return ToolResult(success=False, error=error or "Invalid path")
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
