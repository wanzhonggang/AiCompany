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
            import re
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            }

            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                # Try DuckDuckGo first (faster, cleaner HTML)
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers=headers,
                )

                # If DuckDuckGo fails (blocked in China), fall back to Bing
                if resp.status_code != 200:
                    resp = await client.get(
                        "https://www.bing.com/search",
                        params={"q": query, "setlang": "zh-Hans"},
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        return ToolResult(success=False, error=f"Search unavailable (HTTP {resp.status_code})")

                    text = resp.text
                    results: list[str] = []
                    # Bing results: <li class="b_algo"> each contains <h2><a href="url">title</a></h2> and <p>snippet</p>
                    blocks = re.split(r'<li class="b_algo"', text)
                    for block in blocks[1:]:
                        link_m = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*>((?:(?!</a>).)+)</a>', block, re.DOTALL)
                        snippet_m = re.search(r'<p[^>]*>((?:(?!</p>).)+?)</p>', block, re.DOTALL)
                        if link_m:
                            url = link_m.group(1)
                            title = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
                            snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
                            snippet = re.sub(r'\s+', ' ', snippet)
                            results.append(f"🔗 {title}\n   {snippet}\n   {url}")
                        if len(results) >= 8:
                            break
                else:
                    # DuckDuckGo results
                    text = resp.text
                    results = []
                    blocks = re.split(r'<div class="result results_links', text)
                    for block in blocks[1:]:
                        title_m = re.search(r'class="result__a"[^>]*href="([^"]*)"[^>]*>([^<]+)<', block)
                        snippet_m = re.search(r'class="result__snippet"[^>]*>\s*(.*?)\s*</a>', block, re.DOTALL)
                        if title_m:
                            url = title_m.group(1)
                            title = title_m.group(2).strip()
                            snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip() if snippet_m else ""
                            results.append(f"🔗 {title}\n   {snippet}\n   {url}")
                        if len(results) >= 8:
                            break

                output = "\n\n".join(results) if results else f"No search results found for: {query}"
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
