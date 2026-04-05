"""
agent_ppt.py — Auto-PPT Agent (napkin_ai quality)
Usage: python agent_ppt.py "Create a 5-slide presentation on the life cycle of a star for a 6th-grade class"
"""
import asyncio
import os
import re
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

ROOT_MODULE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_MODULE, ".env"))

# Reuse napkin_ai's generator directly — identical prompts, same LLM logic
from generator import generate_slides as generate_presentation


# ── MCP agentic loop ──────────────────────────────────────────────────────────

async def run_agent(user_request: str, fetch_images: bool = True):
    # Parse num_slides hint from the request (e.g. "5-slide")
    m = re.search(r"(\d+)[- ]slide", user_request, re.IGNORECASE)
    num_slides = int(m.group(1)) if m else 6
    num_slides = max(4, min(12, num_slides))

    docs_dir = os.path.join(ROOT_MODULE, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    
    clean_prompt = re.sub(r'[^\w\s-]', '', user_request).strip()[:60].replace(' ', '_')
    if not clean_prompt:
        clean_prompt = "presentation"
    
    output_path = os.path.join(docs_dir, f"{clean_prompt}.pptx")
    history_dir = os.path.join(ROOT_MODULE, ".history")
    os.makedirs(history_dir, exist_ok=True)
    json_path = os.path.join(history_dir, f"{clean_prompt}.json")
    seq = 1
    while os.path.exists(output_path) or os.path.exists(json_path):
        output_path = os.path.join(docs_dir, f"{clean_prompt}_{seq}.pptx")
        json_path = os.path.join(history_dir, f"{clean_prompt}_{seq}.json")
        seq += 1

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "mcp_server.py")],
    )
    server_params_search = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "web_search_mcp.py")],
    )

    async with stdio_client(server_params) as (read, write), \
               stdio_client(server_params_search) as (read_search, write_search):
        async with ClientSession(read, write) as session, \
                   ClientSession(read_search, write_search) as session_search:
            await session.initialize()
            await session_search.initialize()

            # ── PLAN: one LLM call generates the full structured presentation ──
            print(f"🧠  Generating full presentation plan ({num_slides} slides)...")
            try:
                data = generate_presentation(user_request, "", num_slides)
            except Exception as e:
                print(f"⚠️  Generation failed ({e}), using fallback outline.")
                data = {
                    "title": user_request[:60],
                    "subtitle": "An AI-generated presentation",
                    "slides": [
                        {"title": t, "layout": "bullets",
                         "bullets": [f"Key point about {t}." for _ in range(4)],
                         "description": f"Overview of {t}.",
                         "image_query": f"{t} photo",
                         "notes": f"Discuss {t}."}
                        for t in ["Introduction", "Key Concepts", "Details", "Examples", "Conclusion"]
                    ],
                }

            import json
            with open(json_path, "w") as f:
                json.dump(data, f)

            print(f"📋  Title: {data['title']}")
            print(f"📋  Slides: {[s['title'] for s in data['slides']]}\n")

            # ── TOOL: create_presentation ─────────────────────────────────────
            r = await session.call_tool("create_presentation", {"output_path": output_path})
            print(r.content[0].text)

            # ── TOOL: search_image (fetch cover) ──────────────────────────────
            cover_url = ""
            if fetch_images:
                cover_query = data.get("cover_image_query") or data.get("title")
                r_img = await session_search.call_tool("search_image", {"query": cover_query})
                cover_url = r_img.content[0].text

            # ── TOOL: add_title_slide ─────────────────────────────────────────
            r = await session.call_tool("add_title_slide", {
                "title":        data["title"],
                "subtitle":     data.get("subtitle", ""),
                "image_url":    cover_url
            })
            print(r.content[0].text)

            # ── LOOP: one add_slide call per slide ────────────────────────────
            for i, slide in enumerate(data["slides"], 1):
                print(f"✍️   Slide {i}/{len(data['slides'])}: {slide['title']} [{slide.get('layout','bullets')}]")
                slide_url = ""
                if fetch_images and slide.get("image_query"):
                    r_img = await session_search.call_tool("search_image", {"query": slide["image_query"]})
                    slide_url = r_img.content[0].text

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
                    "notes":         slide.get("notes", "")
                })
                print(f"    ↳ {r.content[0].text}")

            # ── TOOL: save_presentation ───────────────────────────────────────
            r = await session.call_tool("save_presentation", {})
            print(f"\n✅  {r.content[0].text}")
            print(f"📁  {os.path.abspath(output_path)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python agent_ppt.py "Your presentation request here"')
        print('       python agent_ppt.py "..." --no-images   (skip Pexels fetching)')
        sys.exit(1)
    args = sys.argv[1:]
    no_images = "--no-images" in args
    request = " ".join(a for a in args if a != "--no-images")
    asyncio.run(run_agent(request, fetch_images=not no_images))
