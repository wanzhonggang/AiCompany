import asyncio
import sys
import threading
from pathlib import Path
from typing import Any

from .base import BaseTool, ToolSpec, ToolResult


class BrowserSession:
    """Owns Playwright state outside FastAPI's asyncio loop.

    On Windows, Playwright launches a browser driver process. Some ASGI setups
    use SelectorEventLoop, which cannot create asyncio subprocess transports.
    Running the sync Playwright API in a worker thread avoids that server-loop
    limitation and keeps one persistent browser session for the AI employee.
    """

    def __init__(self):
        self.playwright: Any = None
        self.browser: Any = None
        self.page: Any = None
        self.lock = threading.RLock()

    def _prepare_thread_loop_policy(self):
        if sys.platform == "win32" and hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    def ensure_page(self, headless: bool = False):
        try:
            self._prepare_thread_loop_policy()
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright 未安装。请在后端环境执行："
                "pip install -r backend/requirements.txt，然后执行：python -m playwright install chromium"
            ) from exc

        if self.playwright is None:
            self.playwright = sync_playwright().start()

        if self.browser is None or not self.browser.is_connected():
            self.browser = self.playwright.chromium.launch(headless=headless)

        if self.page is None or self.page.is_closed():
            self.page = self.browser.new_page(viewport={"width": 1366, "height": 900})

        return self.page

    def close(self):
        if self.browser is not None:
            self.browser.close()
            self.browser = None
            self.page = None
        if self.playwright is not None:
            self.playwright.stop()
            self.playwright = None


SESSION = BrowserSession()


def _page_summary(page: Any, limit: int = 5000) -> dict:
    title = page.title()
    url = page.url
    text = page.locator("body").inner_text(timeout=5000)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit] + "...[truncated]"
    return {"title": title, "url": url, "text": text}


def _screenshot_path(path: str | None = None) -> Path:
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
    else:
        candidate = Path.cwd() / "browser_screenshots" / "latest.png"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate.resolve()


async def _run_browser(fn):
    return await asyncio.to_thread(fn)


class BrowserOpenTool(BaseTool):
    name = "browser_open"
    category = "browser"
    description = (
        "Open a real Chromium browser window with Playwright and navigate to a URL. "
        "Use this when the user asks to open a browser, open Baidu/Google/Bing, navigate to a website, "
        "visit a URL, inspect an interactive page, or do anything that requires a visible browser."
    )
    timeout_seconds = 90

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to open, for example https://example.com"},
                    "headless": {
                        "type": "boolean",
                        "description": "Whether to run without a visible browser window. Defaults to false.",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, url: str = "", headless: bool = False, **kwargs) -> ToolResult:
        if not url:
            return ToolResult(success=False, error="URL is required")

        def op():
            with SESSION.lock:
                page = SESSION.ensure_page(headless=headless)
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                return _page_summary(page)

        try:
            return ToolResult(success=True, data=await _run_browser(op))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BrowserClickTool(BaseTool):
    name = "browser_click"
    category = "browser"
    description = (
        "Click an element in the currently open browser page using a CSS selector or text selector. "
        "Use this for login buttons, search buttons, links, menus, tabs, checkboxes, and any user-requested click."
    )
    timeout_seconds = 60

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {
                        "type": "string",
                        "description": "Selector to click, such as text=Login, button[type=submit], or #submit",
                    },
                    "wait_after_ms": {
                        "type": "integer",
                        "description": "Milliseconds to wait after clicking. Defaults to 1000.",
                    },
                },
                "required": ["selector"],
            },
        )

    async def execute(self, selector: str = "", wait_after_ms: int = 1000, **kwargs) -> ToolResult:
        if not selector:
            return ToolResult(success=False, error="Selector is required")

        def op():
            with SESSION.lock:
                page = SESSION.ensure_page()
                page.click(selector, timeout=15000)
                page.wait_for_timeout(max(0, min(wait_after_ms, 10000)))
                return _page_summary(page)

        try:
            return ToolResult(success=True, data=await _run_browser(op))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BrowserTypeTool(BaseTool):
    name = "browser_type"
    category = "browser"
    description = (
        "Type text into an input, textarea, or editable field in the currently open browser page. "
        "Use this for search boxes, login forms, text areas, and any browser form input."
    )
    timeout_seconds = 60

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector or Playwright text selector for the field"},
                    "text": {"type": "string", "description": "Text to enter"},
                    "press_enter": {"type": "boolean", "description": "Press Enter after typing. Defaults to false."},
                },
                "required": ["selector", "text"],
            },
        )

    async def execute(
        self,
        selector: str = "",
        text: str = "",
        press_enter: bool = False,
        **kwargs,
    ) -> ToolResult:
        if not selector:
            return ToolResult(success=False, error="Selector is required")

        def op():
            with SESSION.lock:
                page = SESSION.ensure_page()
                page.fill(selector, text, timeout=15000)
                if press_enter:
                    page.press(selector, "Enter")
                    page.wait_for_timeout(1000)
                return _page_summary(page)

        try:
            return ToolResult(success=True, data=await _run_browser(op))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BrowserSnapshotTool(BaseTool):
    name = "browser_snapshot"
    category = "browser"
    description = "Read the current browser page and optionally save a screenshot for visual inspection or debugging."
    timeout_seconds = 60

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "screenshot_path": {
                        "type": "string",
                        "description": "Optional path for a PNG screenshot. Defaults to browser_screenshots/latest.png.",
                    },
                },
            },
        )

    async def execute(self, screenshot_path: str | None = None, **kwargs) -> ToolResult:
        def op():
            with SESSION.lock:
                page = SESSION.ensure_page()
                path = _screenshot_path(screenshot_path)
                page.screenshot(path=str(path), full_page=True)
                summary = _page_summary(page)
                summary["screenshot_path"] = str(path)
                return summary

        try:
            return ToolResult(success=True, data=await _run_browser(op))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BrowserCloseTool(BaseTool):
    name = "browser_close"
    category = "browser"
    description = "Close the Playwright browser controlled by the AI employee."
    timeout_seconds = 30

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={"type": "object", "properties": {}},
        )

    async def execute(self, **kwargs) -> ToolResult:
        def op():
            with SESSION.lock:
                SESSION.close()
                return "Browser closed"

        try:
            return ToolResult(success=True, data=await _run_browser(op))
        except Exception as e:
            return ToolResult(success=False, error=str(e))
