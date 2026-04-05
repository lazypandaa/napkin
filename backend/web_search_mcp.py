import os
import requests
import asyncio
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

server = Server("napkin-web-search-mcp")

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_image",
            description="Search the web for a highly relevant image URL matching the specific query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query (e.g. 'space galaxy')"}
                },
                "required": ["query"],
            },
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name == "search_image":
        query = arguments["query"]
        api_key = os.getenv("PEXELS_API_KEY", "")
        if not api_key or api_key == "your_pexels_api_key_here":
            return [types.TextContent(type="text", text="")]
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": api_key},
                params={"query": query, "per_page": 5, "orientation": "landscape"},
                timeout=10,
            )
            if r.status_code == 200:
                photos = r.json().get("photos", [])
                if photos:
                    return [types.TextContent(type="text", text=photos[0]["src"]["large"])]
        except Exception:
            pass
        return [types.TextContent(type="text", text="")]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
