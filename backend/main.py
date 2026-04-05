"""
http_server.py — FastAPI bridge for the React frontend
Exposes the same /generate, /export, /image-proxy endpoints as napkin_ai/backend/main.py
but drives the MCP ppt tools internally for /export.

Run: uvicorn http_server:app --reload --port 8000
"""
import sys
import os

ROOT_MODULE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT_MODULE, ".env"))

import asyncio
import base64
import io
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pptx import Presentation
from pptx.util import Inches

# Reuse napkin_ai's generator directly (same LLM logic, no duplication)
from generator import generate_slides
import requests as req_lib

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class GenerateRequest(BaseModel):
    topic: str
    requirements: str = ""
    num_slides: int = 6

class ExportRequest(BaseModel):
    presentation: dict
    fetch_images: bool = True

class CanvasExportRequest(BaseModel):
    slides: list[str]  # base64 PNG per slide
    title: str = "presentation"


# ── /generate — identical to napkin_ai backend ────────────────────────────────

@app.post("/generate")
async def generate(req: GenerateRequest):
    try:
        data = generate_slides(req.topic, req.requirements, req.num_slides)
        
        import re, json
        clean_title = re.sub(r'[^\w\s-]', '', data.get('title', 'presentation')).strip()[:60].replace(' ', '_')
        if not clean_title: clean_title = "presentation"
        
        history_dir = os.path.join(ROOT_MODULE, ".history")
        os.makedirs(history_dir, exist_ok=True)
        
        json_path = os.path.join(history_dir, f"{clean_title}.json")
        seq = 1
        while os.path.exists(json_path):
            json_path = os.path.join(history_dir, f"{clean_title}_{seq}.json")
            seq += 1
            
        with open(json_path, "w") as f:
            json.dump(data, f)
            
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
async def get_history():
    history_dir = os.path.join(ROOT_MODULE, ".history")
    history = []
    if os.path.exists(history_dir):
        files = []
        for filename in os.listdir(history_dir):
            if filename.endswith(".json"):
                files.append(os.path.join(history_dir, filename))
        
        files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        import json
        for filepath in files:
            with open(filepath, "r") as f:
                try:
                    history.append(json.load(f))
                except:
                    pass
    return history


# ── /export — drives MCP server to build the .pptx ───────────────────────────

async def _build_pptx_via_mcp(presentation: dict, fetch_images: bool) -> bytes:
    docs_dir = os.path.join(ROOT_MODULE, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    filename = f"{presentation.get('title', 'presentation').replace(' ', '_')}.pptx"
    output_path = os.path.join(docs_dir, filename)

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

            await session.call_tool("create_presentation", {"output_path": output_path})

            # Title slide
            cover_query = presentation.get("cover_image_query") or presentation.get("title")
            cover_url = ""
            if fetch_images:
                r_img = await session_search.call_tool("search_image", {"query": cover_query})
                cover_url = r_img.content[0].text

            await session.call_tool("add_title_slide", {
                "title":        presentation["title"],
                "subtitle":     presentation.get("subtitle", ""),
                "image_url":    cover_url
            })

            # Content slides
            for slide in presentation.get("slides", []):
                slide_url = ""
                if fetch_images and slide.get("image_query"):
                    r_img = await session_search.call_tool("search_image", {"query": slide["image_query"]})
                    slide_url = r_img.content[0].text

                await session.call_tool("add_slide", {
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

            await session.call_tool("save_presentation", {})

    with open(output_path, "rb") as f:
        data = f.read()
    # Keeping the file in docs/ directory
    return data


@app.post("/export")
async def export(req: ExportRequest):
    try:
        pptx_bytes = await _build_pptx_via_mcp(req.presentation, req.fetch_images)
        return Response(
            content=pptx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": "attachment; filename=presentation.pptx"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export-canvas")
async def export_canvas(req: CanvasExportRequest):
    try:
        prs = Presentation()
        prs.slide_width  = Inches(13.33)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]
        for b64 in req.slides:
            slide = prs.slides.add_slide(blank)
            img_bytes = base64.b64decode(b64)
            slide.shapes.add_picture(
                io.BytesIO(img_bytes),
                Inches(0), Inches(0),
                prs.slide_width, prs.slide_height,
            )
        buf = io.BytesIO()
        prs.save(buf)

        import re
        clean_title = re.sub(r'[^\w\s-]', '', req.title).strip()[:60].replace(' ', '_')
        if not clean_title:
            clean_title = "presentation"

        docs_dir = os.path.join(ROOT_MODULE, "docs")
        os.makedirs(docs_dir, exist_ok=True)
        docs_path = os.path.join(docs_dir, f"{clean_title}.pptx")
        seq = 1
        while os.path.exists(docs_path):
            docs_path = os.path.join(docs_dir, f"{clean_title}_{seq}.pptx")
            seq += 1

        final_filename = os.path.basename(docs_path)
        with open(docs_path, "wb") as f:
            f.write(buf.getvalue())

        return Response(
            content=buf.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": f"attachment; filename={final_filename}"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── /image-proxy — identical to napkin_ai backend ────────────────────────────

@app.get("/image-proxy")
async def image_proxy(query: str):
    api_key = os.getenv("PEXELS_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=404, detail="No API key")
    try:
        r = req_lib.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 5, "orientation": "landscape"},
            timeout=10,
        )
        photos = r.json().get("photos", [])
        if not photos:
            raise HTTPException(status_code=404, detail="No images found")
        img = req_lib.get(photos[0]["src"]["large"], timeout=10)
        if img.status_code == 200:
            return Response(content=img.content, media_type=img.headers.get("Content-Type", "image/jpeg"))
    except HTTPException:
        raise
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Image not found")
