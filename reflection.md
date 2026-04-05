# Reflection Document — Auto-PPT Agent

**Course:** AI Agents & MCP Architecture  
**Project:** Auto-PPT — a dual-MCP agentic system that turns a single sentence into a fully themed `.pptx`

---

## 1. Project Overview

The goal of this project was to build an autonomous agent that accepts a single natural-language prompt and produces a fully styled PowerPoint presentation — without any human intervention in between. The system had to satisfy three hard constraints:

1. The agent must **plan before acting** — no slide should be written until the full outline is decided
2. At least **two MCP servers** must be orchestrated together
3. The output must be a real, downloadable `.pptx` file with visual quality comparable to a human-made deck

The final system achieves all three. A React frontend lets users type a topic and click Generate; within seconds a `.pptx` downloads automatically. A CLI path (`agent_ppt.py`) provides the same capability without a browser. Both paths share the same LLM planning logic and the same two MCP servers.

---

## 2. Architecture Decisions

### Why Dual MCP?

The two MCP servers have a clean separation of responsibility:

- `mcp_server.py` owns everything related to **file creation** — it holds the in-memory `python-pptx` `Presentation` object, renders each slide with the correct layout, colors, and typography, and finally flushes it to disk. It never touches the internet.
- `web_search_mcp.py` owns **image retrieval** — it queries the Pexels API with a topic-specific search string and returns a URL. It knows nothing about PowerPoint.

This separation means either server can be swapped independently. If Pexels is replaced by Unsplash tomorrow, only `web_search_mcp.py` changes. If the slide renderer is upgraded from `python-pptx` to a PDF engine, only `mcp_server.py` changes. The agent and the frontend are untouched in both cases.

### Why stdio transport?

stdio was chosen over HTTP/SSE for the MCP transport because:

- No port management — the backend spawns each server as a subprocess and communicates over stdin/stdout, so there are no port conflicts and no server lifecycle to manage
- Simpler deployment — the MCP servers are just Python scripts, not long-running services
- Matches the assignment's intent of demonstrating the MCP protocol at the process boundary level

### Why FastAPI as the bridge?

The React frontend cannot spawn Python subprocesses directly. FastAPI acts as a thin bridge: it receives JSON from the browser, calls `generate_slides()` for the LLM planning step, then opens `ClientSession` connections to both MCP servers via stdio to build the `.pptx`. The frontend never needs to know that MCP exists.

---

## 3. The Agentic Loop in Detail

```
User Prompt
    │
    ▼
LLM (Qwen2.5-7B-Instruct) — single prompt, returns full JSON outline
    │   {title, subtitle, slides: [{title, layout, bullets, image_query, notes}, ...]}
    ▼
MCP Server 2: create_presentation(output_path)
    │
    ▼
for each slide in plan:
    ├── MCP Server 1: search_image(image_query)  → image URL
    └── MCP Server 2: add_title_slide / add_slide (with image URL)
    │
    ▼
MCP Server 2: save_presentation()  →  .pptx written to disk
```

The critical design choice is that **the LLM plans the entire deck in a single inference call** before any MCP tool is invoked. This satisfies the "agentic planning" requirement — the agent reasons about the full structure first, then executes. It also means the LLM only needs to be called once, keeping latency low and token usage predictable.

---

## 4. Where Did the Agent Fail Its First Attempt?

### Failure 1 — JSON parsing crash

The first end-to-end run crashed immediately after the LLM call with a `JSONDecodeError`. The model returned the slide outline wrapped in a markdown code fence:

```
```json
[{"title": "Introduction", ...}]
```
```

`json.loads()` cannot parse this. The fix was a `_extract_json()` helper that:

1. Strips markdown fences with a regex (```` ```json ... ``` ````)
2. Slices from the first `[` or `{` to the last `]` or `}` to isolate the JSON substring
3. Falls back to a hardcoded default outline (`["Introduction", "Key Points", "Details", "Examples", "Conclusion"]`) if parsing still fails — so the agent always produces *something* rather than crashing

This fallback is important for robustness: a partial presentation is more useful than a stack trace.

### Failure 2 — Empty bullets list

After fixing JSON parsing, several slides rendered as blank content areas. The LLM occasionally emitted `"bullets": []` for abstract slides like "Conclusion" or "Thank You". The `mcp_server.py` `add_slide` tool received an empty list and drew nothing.

The fix was a per-slide fallback in the generator: if `bullets` is empty after parsing, it is replaced with `[f"Key point about {title}."] * 4`. This guarantees the MCP tool always receives valid, non-empty input.

### Failure 3 — UI vs downloaded PPTX mismatch

The original export path used `html2canvas` to screenshot each slide's DOM node and embed the screenshots as images in the PPTX via `/export-canvas`. This produced blank slides because:

- `setPresentation(data)` is an async React state update — the slides had not re-rendered to the DOM yet when `exportPptx` was called immediately after
- Even when timing was corrected, `html2canvas` could not capture cross-origin Pexels images due to CORS restrictions, so all images were missing from the screenshots

The fix was to abandon the canvas screenshot approach entirely and route the export through `/export` instead. This sends the raw presentation JSON to the FastAPI backend, which passes it to `mcp_server.py` via MCP. The MCP server was already built to mirror the UI's visual style exactly (same colors, same layout logic, same Pexels image fetching), so the downloaded PPTX now matches what the user sees in the browser.

### Failure 4 — Image deduplication

When multiple slides had similar topics (e.g., "Introduction" and "Overview"), the Pexels API returned the same top result for both, causing identical images on adjacent slides. The fix was a `_used_image_urls` set in `mcp_server.py` that tracks which URLs have already been used and skips them, forcing the API to return the next available unique image.

---

## 5. How Did MCP Prevent Hardcoded Scripts?

Without MCP, the natural approach is a single Python script that calls `python-pptx` directly in a fixed sequence: create file → loop over a hardcoded list → save. The slide count, order, and content are all baked in at write-time.

MCP inverts this in several important ways:

**The agent decides the tool call sequence at runtime.** The LLM plans the outline first, then issues one `add_slide` tool call per title it chose. If the LLM decides a 4-slide deck is enough, only 4 calls are made. If it plans 8, 8 calls are made — no code change required. The number and content of slides is a runtime decision, not a compile-time one.

**Tools are contracts, not implementations.** The agent only knows that `add_slide` accepts `{title, layout, bullets, notes}` and returns a confirmation string. How the slide is rendered — colors, fonts, layout geometry, image placement — is entirely inside `mcp_server.py` and invisible to the agent. Swapping the visual theme or switching from `python-pptx` to a different rendering library requires zero changes to `agent_ppt.py`.

**Multi-client reuse.** The same `mcp_server.py` is used by three different clients in this project: the CLI agent (`agent_ppt.py`), the FastAPI web backend (`http_server.py`), and indirectly by the original `backend/main.py`. All three connect over stdio and call the same tools. This is impossible with a hardcoded script — you would need three separate copies of the rendering logic.

**Separation of concerns enforced by the protocol.** The agent loop contains only planning and LLM calls. All file I/O and rendering lives in the MCP server. This boundary is enforced by the stdio transport — the agent literally cannot call `python-pptx` functions directly. The protocol makes the architecture clean by construction.

**Dynamic tool discovery.** The agent calls `list_tools()` at startup and receives the tool schemas at runtime. If a new tool like `add_transition` or `set_theme` is added to the MCP server, the agent can discover and use it without any changes to the agent code. A hardcoded script has no equivalent mechanism.

---

## 6. What I Would Do Differently

**Streaming progress updates.** Currently the frontend shows a spinner for the entire generation duration (typically 15–30 seconds). A better UX would stream slide-by-slide progress back to the browser via Server-Sent Events — "Planning outline… Adding slide 1/6… Fetching image…" — so the user knows the system is working.

**Persistent presentation history.** The current system generates and immediately downloads. There is no server-side storage of past presentations. Adding a simple SQLite store with a history panel in the sidebar would let users revisit and re-export previous decks.

**Better LLM prompting for layout diversity.** The LLM tends to default to `bullets` layout for most slides. A more explicit prompt that requires at least one `stats`, one `two_column`, and one `quote` slide per deck would produce more visually varied presentations.

**Async MCP calls for images.** Currently, image fetching is sequential — each slide waits for its image before the next slide starts. Since the Pexels API calls are independent, they could be parallelised with `asyncio.gather()`, cutting the image-fetching phase from O(n) to O(1) in wall-clock time.

---

## 7. Key Takeaways

- **MCP is most valuable at the boundary between planning and execution.** The LLM is good at deciding *what* to do; MCP tools are good at *doing* it. Keeping these two concerns in separate processes with a typed protocol between them produces systems that are easier to test, extend, and debug than monolithic agent scripts.

- **Robustness requires fallbacks at every parsing boundary.** LLMs are non-deterministic. Any point where the agent parses LLM output needs a fallback — not just error logging, but a sensible default that keeps the pipeline running.

- **The export path is as important as the generation path.** A beautiful in-browser preview is worthless if the downloaded file looks different. Ensuring the MCP server's rendering logic mirrors the frontend's CSS was the most detail-intensive part of the project, but it is what makes the system feel complete.
