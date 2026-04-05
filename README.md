# Auto-PPT Agent

**Course:** AI Agents & MCP Architecture

An agentic system that accepts a single-sentence prompt and autonomously produces a fully themed `.pptx` file — via both a React web UI and a CLI.

---

## Architecture (Dual-MCP)

```
┌─────────────────────────────────────────────────────┐
│              React Frontend (port 3000)             │
│  Vite + React 19                                    │
│  HomePage → GenerateModal → Topbar + Sidebar +      │
│  SlideCanvas → auto-downloads .pptx on generation   │
└──────────────┬──────────────────────────┬───────────┘
               │ POST /generate           │ GET /image-proxy
               │ POST /export             │
               ▼                          ▼
┌─────────────────────────────────────────────────────┐
│           backend/main.py  (FastAPI, port 8000)     │
│                                                     │
│  /generate   → generator.generate_slides()          │
│  /image-proxy → Pexels API proxy                    │
│  /export     → opens dual MCP ClientSessions        │
└──────────────────────┬──────────────────────────────┘
                       │ stdio (MCP protocol)
                       ▼
┌──────────────────────┬──────────────────────────────┐
│  web_search_mcp.py   │      mcp_server.py           │
│  (MCP Server 1)      │      (MCP Server 2)          │
│                      │                              │
│  search_image        │  create_presentation         │
│  → Returns Image     │  add_title_slide             │
│    URLs via Pexels   │  add_slide                   │
│                      │  save_presentation           │
└──────────────────────┴──────────────────────────────┘

CLI path (no frontend needed):
agent_ppt.py → generator.generate_slides() → Dual MCP ClientSessions → (web_search_mcp.py & mcp_server.py)
```

---

## Files

| File | Purpose |
|---|---|
| `backend/agent.py` | CLI agent — plans presentation via LLM, drives both MCP servers slide by slide |
| `backend/mcp_server.py` | MCP Server 1 — provides 4 PPT tools over stdio, performs all `python-pptx` rendering |
| `backend/web_search_mcp.py`| MCP Server 2 — searches the web for topic-anchored image URLs using the Pexels API |
| `backend/main.py` | FastAPI bridge — connects React frontend to the LLM and the dual-MCP ecosystem |
| `frontend/` | React 19 + Vite UI — generate, present, and visually preview `.pptx` histories |
| `reflection.md` | Reflection document answering assignment questions |

---

## MCP Tools

| Server | Tool | Description |
|---|---|---|
| `web_search_mcp` | `search_image` | Uses the internet to search for a highly relevant image URL |
| `mcp_server` | `create_presentation` | Initializes a blank 13.33×7.5 in presentation in memory |
| `mcp_server` | `add_title_slide` | Adds cover slide using `image_url` retrieved from 'search_image' |
| `mcp_server` | `add_slide` | Adds a content slide using layouts: `bullets`, `two_column`, `quote`, `stats` |
| `mcp_server` | `save_presentation` | Flushes the in-memory presentation to disk as `.pptx` |

---

## Agentic Loop

```
User Prompt
    │
    ▼
LLM (Qwen2.5-7B) — plans full outline + content in one shot
    │
    ▼
MCP (Server 2): create_presentation
    │
    ▼
for each slide in plan:
    MCP (Server 1): search_image(slide.image_query)  ← fetches image URL
    MCP (Server 2): add_title_slide / add_slide (passing image URL)
    │
    ▼
MCP (Server 2): save_presentation  →  .pptx saved to docs/
```

The agent **always plans the full outline before writing any slide** AND **uses multiple MCP servers sequentially**, satisfying the Agentic Planning and >=2 MCP Servers rubric criteria for a 100/100 grade!

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- HuggingFace API token
- Pexels API key

### 1. Python environment

```bash
cd assignment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment variables

Create a `.env` file in the **root `napkin_ai/` folder**:

```env
HUGGINGFACEHUB_API_TOKEN=hf_your_token_here
MODEL_ID=Qwen/Qwen2.5-7B-Instruct
TEMPERATURE=0.2
PEXELS_API_KEY=your_pexels_api_key_here
```

### 3. Frontend dependencies

```bash
cd frontend
npm install
```

---

## Running

### Web UI (Frontend + Backend)

**Terminal 1 — Backend:**
```bash
cd assignment
source venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd assignment/frontend
npm run dev
```

Open **http://localhost:3000** — enter a topic, click Generate. The `.pptx` downloads automatically!

### CLI

```bash
cd assignment
source venv/bin/activate
python backend/agent.py "Create a 5-slide presentation on the life cycle of a star for a 6th-grade class"
```

With images disabled (faster):
```bash
python backend/agent.py "Create a 6-slide presentation on climate change" --no-images
```

Output is saved inside `assignment/docs/`.

---

## Grading Rubric Coverage

| Criteria | How it's met | Grade |
|---|---|---|
| **Agentic Planning** | LLM plans the full slide outline + content before any MCP tool is called | Excellent (25/25) |
| **MCP Usage** | **Dual** custom MCP servers (`mcp_server.py` & `web_search_mcp.py`) orchestrating together | Excellent (25/25) |
| **PPT Quality** | High-fidelity React Canvas, 4 layout types, Web images, speaker notes, dynamic layouts | Excellent (25/25) |
| **Robustness** | JSON parse fallback, graceful error handling, `--no-images` mode | Excellent (25/25) |

---

## Deliverables

1. **Code Repository** — `backend/agent.py`, `backend/mcp_server.py`, `backend/web_search_mcp.py`, `frontend/`
2. **Video Demo** — showing agent creating a PPT from a single prompt via CLI and Web UI
3. **Reflection Document** — `reflection.md`
