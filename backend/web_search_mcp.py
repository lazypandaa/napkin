"""
web_search_mcp.py — MCP Server 1: Image Search
------------------------------------------------
Provides a single MCP tool: search_image

Responsibilities:
  - Accept a text query from the agent or the FastAPI backend
  - Call the Pexels API to find a relevant landscape photo
  - Return the direct image URL as a plain text MCP response

Why a separate MCP server for image search?
  - Clean separation of concerns: this server owns all internet/image logic.
    mcp_server.py (Server 2) owns all file/rendering logic. Neither knows
    about the other's internals.
  - Swappable: replacing Pexels with Unsplash or Google Images only requires
    changes here — the agent and the PPT server are untouched.
  - Independently testable: you can connect to this server alone and call
    search_image without spinning up the PPT server.

Transport: stdio (stdin/stdout pipes)
  Spawned as a subprocess by the agent or FastAPI backend via StdioServerParameters.

Run standalone (for testing):
  python web_search_mcp.py
"""

import os
import asyncio
import requests
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# Load .env from the project root (assignment/.env)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# ── MCP Server instance ───────────────────────────────────────────────────────
# The server name is used for identification in MCP handshake logs.
server = Server("napkin-web-search-mcp")


# ── Tool registry ─────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """
    Advertise the tools this server provides to any connected MCP client.

    Called automatically during the MCP handshake (session.initialize()).
    The client uses the returned schemas to know what tools are available
    and what arguments each tool expects.
    """
    return [
        types.Tool(
            name="search_image",
            description=(
                "Search the Pexels photo library for a high-quality landscape image "
                "matching the given query. Returns a direct image URL string, or an "
                "empty string if no image is found or the API key is missing."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type":        "string",
                        "description": (
                            "Short, concrete search keywords for Pexels "
                            "(e.g. 'space galaxy', 'climate forest', 'solar panel field'). "
                            "Avoid abstract terms — Pexels works best with noun phrases."
                        ),
                    }
                },
                "required": ["query"],
            },
        )
    ]


# ── Tool handler ──────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """
    Dispatch incoming tool calls to the appropriate handler.

    MCP routes all tool calls through this single function. We check the tool
    name and delegate accordingly. Unknown tool names return an error string
    rather than raising an exception so the agent can handle them gracefully.

    Args:
        name:      The tool name as registered in list_tools().
        arguments: Dict of arguments matching the tool's inputSchema.

    Returns:
        A list containing a single TextContent with the result string.
        For search_image: the image URL, or "" if nothing was found.
    """
    if name == "search_image":
        return await _search_image(arguments["query"])

    # Unknown tool — return an error message instead of crashing
    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def _search_image(query: str) -> list[types.TextContent]:
    """
    Call the Pexels API and return the URL of the best matching landscape photo.

    Search strategy:
      - Requests 5 results and returns the first one (highest relevance rank)
      - Filters to landscape orientation to match the 16:9 slide aspect ratio
      - Uses the "large" size variant (~1200px wide) — good quality, fast load

    Args:
        query: The Pexels search string.

    Returns:
        A single-item list with a TextContent containing the image URL,
        or an empty string if the API key is missing, the query returns no
        results, or any network/API error occurs.
    """
    api_key = os.getenv("PEXELS_API_KEY", "")

    # Guard: if no API key is configured, return empty rather than crashing.
    # The MCP server and agent both handle empty URLs gracefully (no image rendered).
    if not api_key or api_key == "your_pexels_api_key_here":
        return [types.TextContent(type="text", text="")]

    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},  # API key goes in the header, not the URL
            params={
                "query":       query,
                "per_page":    5,                 # fetch 5 so we have fallbacks if needed
                "orientation": "landscape",       # match 16:9 slide dimensions
            },
            timeout=10,
        )

        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                # Return the "large" variant URL of the top result
                return [types.TextContent(type="text", text=photos[0]["src"]["large"])]

    except Exception:
        # Swallow all network/parsing errors — the caller handles empty URLs
        pass

    # No results or error — return empty string so the slide renders without an image
    return [types.TextContent(type="text", text="")]


# ── Server entry point ────────────────────────────────────────────────────────

async def main():
    """Start the MCP server and listen on stdio until the parent process closes the pipe."""
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
