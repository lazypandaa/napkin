import os
import json
import re
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

client = InferenceClient(
    model=os.getenv("MODEL_ID", "Qwen/Qwen2.5-7B-Instruct"),
    token=os.getenv("HUGGINGFACEHUB_API_TOKEN"),
)

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
    prompt = (
        f"Topic: {topic}\n"
        f"Requirements: {requirements if requirements else 'Professional presentation for a general audience'}\n"
        f"Number of slides: {num_slides}\n\n"
        f"Generate a complete, detailed presentation. Make sure 'image_query' relies on both the main topic and the individual slide focus for optimal image search."
    )

    response = client.chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=3000,
        temperature=float(os.getenv("TEMPERATURE", 0.3)),
    )

    raw = response.choices[0].message.content.strip()

    import re
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
    if match:
        raw = match.group(1).strip()
    else:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]

    import json
    data = json.loads(raw)

    # To ensure image queries are always extremely relevant, we inject the user's primary topic
    # alongside the LLM's suggested keywords if it's too generic, per the user's suggestion.
    clean_topic = ' '.join(w for w in topic.split() if w.lower() not in ('a', 'an', 'the', 'of', 'for', 'about', 'on', 'create', 'presentation', 'slide')).strip()
    
    for slide in data.get("slides", []):
        suggested = slide.get("image_query", "")
        # Blend the core topic explicitly per user request for maximal relevance
        slide["image_query"] = f"{clean_topic[:20]} {suggested}".strip()

    return data
