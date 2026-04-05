# Reflection Document — Auto-PPT Agent

## Where did your agent fail its first attempt?

The first attempt failed at the **JSON parsing step** after the planning LLM call.  
The model returned the slide-title array wrapped in a markdown code fence (` ```json ... ``` `), which caused `json.loads()` to raise a `JSONDecodeError` immediately, crashing the entire run before a single MCP tool was called.

The fix was a `_extract_json()` helper that:
1. Strips markdown fences with a regex before parsing
2. Locates the first `[` / `{` and last `]` / `}` to slice out the JSON substring
3. Falls back to a hardcoded default outline (`["Introduction", "Key Points", "Details", "Examples", "Conclusion"]`) if parsing still fails — so the agent always produces *something* rather than crashing

A second failure occurred when the LLM occasionally returned an empty `"bullets"` list for a slide (it sometimes emitted `"bullets": []` for abstract titles like "Conclusion"). The per-slide fallback `[f"Key point about {title}."] * 4` ensured the MCP `add_slide` tool always received valid input.

---

## How did MCP prevent you from writing hardcoded scripts?

Without MCP, the natural approach is a single Python script that calls `python-pptx` directly in a fixed sequence: create file → loop over a hardcoded list → save. The slide count, order, and content are all baked in at write-time.

MCP inverts this:

- **The agent decides the tool call sequence at runtime.** The LLM plans the outline first, then issues one `add_slide` tool call per title it chose. If the LLM decides a 4-slide deck is enough, only 4 calls are made. If it plans 8, 8 calls are made — no code change required.
- **Tools are contracts, not implementations.** The agent only knows that `add_slide` accepts `{title, bullets, notes}` and returns a confirmation string. How the slide is rendered (colors, fonts, layout) is entirely inside `mcp_server.py` and invisible to the agent. Swapping the theme or switching from `python-pptx` to a different library requires zero changes to `agent_ppt.py`.
- **Multi-client reuse.** The same `mcp_server.py` can be connected to a Claude Desktop session, a CLI script, or a web backend — all without touching the tool implementations. This is impossible with a hardcoded script.
- **Separation of concerns enforced by the protocol.** The agent loop (`agent_ppt.py`) contains only planning and LLM calls. All file I/O lives in the MCP server. This boundary is enforced by the stdio transport — the agent literally cannot call `pptx` functions directly.
