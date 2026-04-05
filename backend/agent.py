"""
agent.py — CLI Agent Entry Point
----------------------------------
Drives the full agentic loop from the command line without a browser.

Flow:
  1. Parse the user's request to extract slide count hint
  2. Call generator.generate_slides() — ONE LLM call that plans the entire deck
  3. Open two MCP ClientSessions over stdio:
       - session       → mcp_server.py   (PPT rendering tools)
       - session_search → web_search_mcp.py (Pexels image search)
  4. Call MCP tools in sequence: create → title slide → N content slides → save
  5. Write the .pptx to docs/ and the JSON plan to .history/

Usage:
  python agent.py "Create a 5-slide presentation on the life cycle of a star"
  python agent.py "Climate change overview" --no-images
"""

import asyncio
import os
import re
import sys
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

# ── Path setup ────────────────────────────────────────────────────────────────
# ROOT_MODULE points to the assignment/ directory so we can locate .env,
# docs/, and .history/ regardless of where the script is invoked from.
ROOT_MODULE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(ROOT_MODULE, ".env"))

# Import the LLM planning function from the same backend package
from generator import generate_slides as generate_presentation


# ── Main agentic loop ─────────────────────────────────────────────────────────

async def run_agent(user_request: str, fetch_images: bool = True):
    """
    Execute the full plan → search → build → save pipeline for a single request.

    Args:
        user_request:  The raw user prompt, e.g. "5-slide deck on black holes".
        fetch_images:  If False, skips all Pexels API calls (faster, offline-safe).
    """

    # ── Step 1: Extract slide count from the request ──────────────────────────
    # Looks for patterns like "5-slide" or "5 slide" in the prompt.
    # Clamps to [4, 12] to avoid trivially short or excessively long decks.
    m = re.search(r"(\d+)[- ]slide", user_request, re.IGNORECASE)
    num_slides = int(m.group(1)) if m else 6
    num_slides = max(4, min(12, num_slides))

    # ── Step 2: Prepare output paths ─────────────────────────────────────────
    # docs/    → final .pptx files (committed to repo, gitignored by *.pptx rule)
    # .history/ → JSON plan files for debugging and history panel in the UI
    docs_dir = os.path.join(ROOT_MODULE, "docs")
    os.makedirs(docs_dir, exist_ok=True)

    # Sanitise the prompt into a safe filename (max 60 chars, underscores)
    clean_prompt = re.sub(r'[^\w\s-]', '', user_request).strip()[:60].replace(' ', '_')
    if not clean_prompt:
        clean_prompt = "presentation"

    output_path = os.path.join(docs_dir, f"{clean_prompt}.pptx")

    # Avoid overwriting existing files by appending a numeric suffix
    history_dir = os.path.join(ROOT_MODULE, ".history")
    os.makedirs(history_dir, exist_ok=True)
    json_path = os.path.join(history_dir, f"{clean_prompt}.json")

    seq = 1
    while os.path.exists(output_path) or os.path.exists(json_path):
        output_path = os.path.join(docs_dir,    f"{clean_prompt}_{seq}.pptx")
        json_path   = os.path.join(history_dir, f"{clean_prompt}_{seq}.json")
        seq += 1

    # ── Step 3: Configure MCP server subprocess parameters ───────────────────
    # Each MCP server is launched as a child process communicating over stdio.
    # StdioServerParameters tells the MCP client which Python executable and
    # script to spawn — no ports, no network, just stdin/stdout pipes.
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
    )
    server_params_search = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "web_search_mcp.py")],
    )

    # ── Step 4: Open both MCP sessions concurrently ───────────────────────────
    # Both servers are started at the same time. We hold both sessions open for
    # the entire duration of the loop so we can interleave search + render calls.
    async with stdio_client(server_params)        as (read, write), \
               stdio_client(server_params_search) as (read_search, write_search):
        async with ClientSession(read, write)                   as session, \
                   ClientSession(read_search, write_search)     as session_search:

            # Handshake — both servers must acknowledge before tools can be called
            await session.initialize()
            await session_search.initialize()

            # ── PLAN: single LLM call produces the full structured outline ────
            # This is the "agentic planning" step — the agent reasons about the
            # entire presentation before writing a single slide.
            print(f"🧠  Generating full presentation plan ({num_slides} slides)...")
            try:
                data = generate_presentation(user_request, "", num_slides)
            except Exception as e:
                # If the LLM call or JSON parsing fails entirely, fall back to a
                # minimal hardcoded outline so the pipeline always produces output.
                print(f"⚠️  Generation failed ({e}), using fallback outline.")
                data = {
                    "title":    user_request[:60],
                    "subtitle": "An AI-generated presentation",
                    "slides": [
                        {
                            "title":       t,
                            "layout":      "bullets",
                            "bullets":     [f"Key point about {t}." for _ in range(4)],
                            "description": f"Overview of {t}.",
                            "image_query": f"{t} photo",
                            "notes":       f"Discuss {t}.",
                        }
                        for t in ["Introduction", "Key Concepts", "Details", "Examples", "Conclusion"]
                    ],
                }

            # Persist the JSON plan for debugging and the UI history panel
            with open(json_path, "w") as f:
                json.dump(data, f)

            print(f"📋  Title: {data['title']}")
            print(f"📋  Slides: {[s['title'] for s in data['slides']]}\n")

            # ── TOOL CALL: create_presentation ────────────────────────────────
            # Initialises an empty python-pptx Presentation object inside the
            # MCP server process and registers the output path for save_presentation.
            r = await session.call_tool("create_presentation", {"output_path": output_path})
            print(r.content[0].text)

            # ── TOOL CALL: search_image (cover image) ─────────────────────────
            # Fetch a cover image for the title slide from Pexels.
            # Uses cover_image_query if the LLM provided one, otherwise falls
            # back to the presentation title as the search query.
            cover_url = ""
            if fetch_images:
                cover_query = data.get("cover_image_query") or data.get("title")
                r_img   = await session_search.call_tool("search_image", {"query": cover_query})
                cover_url = r_img.content[0].text

            # ── TOOL CALL: add_title_slide ────────────────────────────────────
            # Renders the cover slide: large title, subtitle, and the cover image
            # on the right half of the slide (mirrors TitleSlide in SlideCard.jsx).
            r = await session.call_tool("add_title_slide", {
                "title":     data["title"],
                "subtitle":  data.get("subtitle", ""),
                "image_url": cover_url,
            })
            print(r.content[0].text)

            # ── LOOP: one add_slide call per planned content slide ────────────
            # For each slide in the plan:
            #   1. Fetch a relevant image from Pexels (if images enabled)
            #   2. Call add_slide with the full slide data + image URL
            # The layout field determines which renderer runs inside mcp_server.py
            for i, slide in enumerate(data["slides"], 1):
                print(f"✍️   Slide {i}/{len(data['slides'])}: {slide['title']} [{slide.get('layout', 'bullets')}]")

                # Fetch a slide-specific image using the LLM-generated image_query
                slide_url = ""
                if fetch_images and slide.get("image_query"):
                    r_img     = await session_search.call_tool("search_image", {"query": slide["image_query"]})
                    slide_url = r_img.content[0].text

                # Pass all possible layout fields — the MCP server ignores fields
                # that don't apply to the chosen layout, so it's safe to send all.
                r = await session.call_tool("add_slide", {
                    "title":         slide["title"],
                    "layout":        slide.get("layout", "bullets"),
                    "bullets":       slide.get("bullets", []),
                    "left_bullets":  slide.get("left_bullets", []),
                    "right_bullets": slide.get("right_bullets", []),
                    "quote":         slide.get("quote", ""),
                    "author":        slide.get("author", ""),
                    "stats":         slide.get("stats", []),
                    "description":   slide.get("description", ""),
                    "image_url":     slide_url,
                    "notes":         slide.get("notes", ""),
                })
                print(f"    ↳ {r.content[0].text}")

            # ── TOOL CALL: save_presentation ──────────────────────────────────
            # Flushes the in-memory Presentation object to disk at output_path.
            # Must be called last — calling it before all slides are added would
            # produce an incomplete file.
            r = await session.call_tool("save_presentation", {})
            print(f"\n✅  {r.content[0].text}")
            print(f"📁  {os.path.abspath(output_path)}")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python agent.py "Your presentation request here"')
        print('       python agent.py "..." --no-images   (skip Pexels fetching)')
        sys.exit(1)

    args      = sys.argv[1:]
    no_images = "--no-images" in args
    # Join all non-flag arguments as the user request
    request   = " ".join(a for a in args if a != "--no-images")

    asyncio.run(run_agent(request, fetch_images=not no_images))
