"""
generator.py — LLM Planning Layer
----------------------------------
Responsible for the PLAN phase of the agentic loop.

Calls the HuggingFace Inference API (Qwen2.5-7B-Instruct) with a structured
system prompt and returns a fully-formed presentation dict that the MCP tools
can consume directly — no further LLM calls are needed after this.

The returned dict shape:
{
  "title": str,
  "subtitle": str,
  "cover_image_query": str,       # Pexels search query for the title slide
  "slides": [
    {
      "title": str,
      "layout": "bullets" | "two_column" | "quote" | "stats",
      "bullets": [str, ...],       # used by bullets layout
      "left_bullets": [str, ...],  # used by two_column layout
      "right_bullets": [str, ...], # used by two_column layout
      "quote": str,                # used by quote layout
      "author": str,               # used by quote layout
      "stats": [{"value": str, "label": str}, ...],  # used by stats layout
      "description": str,
      "image_query": str,          # Pexels search query for this slide
      "notes": str                 # speaker notes
    },
    ...
  ]
}
"""

import os
import json
import re
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# Load .env from the project root (one level above backend/)
load_dotenv()

# ── HuggingFace Inference client ──────────────────────────────────────────────
# MODEL_ID defaults to Qwen2.5-7B-Instruct — a strong instruction-following
# model that reliably returns structured JSON when prompted correctly.
client = InferenceClient(
    model=os.getenv("MODEL_ID", "Qwen/Qwen2.5-7B-Instruct"),
    token=os.getenv("HUGGINGFACEHUB_API_TOKEN"),
)

# ── System prompt ─────────────────────────────────────────────────────────────
# This prompt is the core of the planning step. It instructs the LLM to:
#   1. Return ONLY valid JSON (no markdown fences, no prose)
#   2. Follow a strict schema that maps 1:1 to the MCP tool inputs
#   3. Produce 4-6 bullets per slide so content slides are never empty
#   4. Use short, concrete image_query values that work well with Pexels
#   5. Support all four layout types with their required fields
SYSTEM_PROMPT = """You are an expert presentation designer. Generate a comprehensive, well-structured presentation.

Return ONLY valid JSON — no markdown, no explanation, nothing else. Use this exact schema:
{
  "title": "Main Presentation Title",
  "subtitle": "A compelling subtitle or tagline",
  "cover_image_query": "1-4 search keywords for Pexels representing the overarching presentation topic (e.g. 'space galaxy', 'pyramid desert')",
  "slides": [
    {
      "title": "Slide Title",
      "layout": "bullets",
      "bullets": [
        "First key point",
        "Second key point",
        "Third key point"
      ],
      "description": "2-3 sentence paragraph providing context.",
      "image_query": "1-4 search keywords combining the presentation topic and this slide's subject. Must be highly relevant noun phrases (e.g., 'star nebula', 'egypt desert pyramid'). Do not use complex sentences.",
      "notes": "Detailed speaker notes."
    }
  ]
}

Rules:
- Each slide MUST have 4-6 bullets, each bullet must be a complete informative sentence
- Each slide MUST have a description paragraph of 2-3 sentences
- Each slide MUST have an image_query consisting of 1-4 highly generic keywords optimal for Pexels image search. Never use abstract terms.
- layout options: "bullets", "two_column", "quote", "stats"
- For "stats" layout add a "stats" array: [{"value": "85%", "label": "adoption rate"}, ...]
- For "quote" layout add "quote" and "author" fields
- For "two_column" layout split bullets into "left_bullets" and "right_bullets" (3 each)
- Generate exactly the requested number of slides"""


def generate_slides(topic: str, requirements: str = "", num_slides: int = 6) -> dict:
    """
    Call the LLM once to plan the entire presentation outline and content.

    This is the sole LLM call in the agentic loop — the agent plans everything
    upfront before any MCP tool is invoked, satisfying the 'agentic planning'
    requirement.

    Args:
        topic:        The user's presentation topic (e.g. "Climate Change").
        requirements: Optional extra instructions (e.g. "target audience: executives").
        num_slides:   How many content slides to generate (excluding the title slide).

    Returns:
        A dict matching the schema described in the module docstring.
        Always returns a valid dict — raises only on unrecoverable LLM/network errors.
    """

    # Build the user message — topic + requirements + slide count in one shot
    prompt = (
        f"Topic: {topic}\n"
        f"Requirements: {requirements if requirements else 'Professional presentation for a general audience'}\n"
        f"Number of slides: {num_slides}\n\n"
        f"Generate a complete, detailed presentation. Make sure 'image_query' relies on both the main topic and the individual slide focus for optimal image search."
    )

    # ── LLM inference ─────────────────────────────────────────────────────────
    # max_tokens=3000 is enough for ~10 slides with full content.
    # temperature is kept low (0.2-0.3) to reduce hallucination and keep JSON valid.
    response = client.chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=3000,
        temperature=float(os.getenv("TEMPERATURE", 0.3)),
    )

    raw = response.choices[0].message.content.strip()

    # ── JSON extraction ────────────────────────────────────────────────────────
    # LLMs often wrap JSON in markdown code fences (```json ... ```) even when
    # told not to. We handle this with two fallback strategies:
    #   1. Regex strip of ```json ... ``` fences
    #   2. Substring slice from first '{' to last '}' to discard any surrounding prose
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        # Strategy 1: strip markdown fence
        raw = match.group(1).strip()
    else:
        # Strategy 2: find the outermost JSON object boundaries
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]

    data = json.loads(raw)

    # ── Image query enrichment ─────────────────────────────────────────────────
    # The LLM sometimes returns generic image queries like "technology" or "people".
    # We prepend the core topic keywords to every slide's image_query to ensure
    # Pexels returns images that are visually relevant to the presentation subject.
    #
    # Stop words are stripped so "Create a presentation about climate change"
    # becomes "climate change" rather than "Create a presentation about climate change".
    stop_words = {'a', 'an', 'the', 'of', 'for', 'about', 'on', 'create', 'presentation', 'slide'}
    clean_topic = ' '.join(
        w for w in topic.split() if w.lower() not in stop_words
    ).strip()

    for slide in data.get("slides", []):
        suggested = slide.get("image_query", "")
        # Blend the first 20 chars of the core topic with the LLM's suggestion.
        # Capped at 20 chars to keep the Pexels query short and effective.
        slide["image_query"] = f"{clean_topic[:20]} {suggested}".strip()

    return data
