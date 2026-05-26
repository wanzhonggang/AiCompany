from .base import BaseTool, ToolSpec, ToolResult
import httpx


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for information. Provide a search query and get relevant results."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query to look up on the web"}
                },
                "required": ["query"]
            }
        )

    async def execute(self, query: str = "", **kwargs) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
                )
                data = resp.json()
                results = []
                if data.get("AbstractText"):
                    results.append(f"📌 {data['AbstractText']}")
                if data.get("AbstractURL"):
                    results.append(f"🔗 {data['AbstractURL']}")
                for related in data.get("RelatedTopics", [])[:5]:
                    if isinstance(related, dict) and related.get("Text"):
                        results.append(f"• {related['Text']}")
                output = "\n".join(results) if results else f"No results found for: {query}"
                return ToolResult(success=True, data=output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch and read the content of a web page by URL. Returns the text content."

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to fetch"}
                },
                "required": ["url"]
            }
        )

    async def execute(self, url: str = "", **kwargs) -> ToolResult:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "AI-Employee-Bot/1.0"})
                resp.raise_for_status()
                # Simple HTML to text extraction
                text = resp.text
                # Remove script and style
                import re
                text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                if len(text) > 10000:
                    text = text[:10000] + "...[content truncated]"
                return ToolResult(success=True, data=text)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
