#!/usr/bin/env python3
"""
scripts/generate_brief.py

Generates:
  - audio/ai_news_YYYYMMDD.mp3      (spoken script, no citations)
  - audio/ai_news_YYYYMMDD.json     (structured transcript with sources)
  - audio/ai_news_YYYYMMDD.txt      (plain-text transcript + Sources block)
"""

import os
import sys
import json
import time
import datetime as dt
from pathlib import Path

import requests
import feedparser
from openai import OpenAI

# ========= Settings =========

AUDIO_DIR = Path("audio")

MODEL_TEXT = "gpt-4o-mini"
TARGET_MIN = 4.5

# ElevenLabs TTS
VOICE_NAME = "Hannah"
MODEL_TTS = "eleven_multilingual_v2"
STABILITY = 0.3
SIMILARITY = 0.8
STYLE = 0.1
SPEAKER_BOOST = True

VOICE_ID_MAP = {}

SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
]

# ========= Helpers =========

def denver_date_today():
    import pytz
    tz = pytz.timezone("America/Denver")
    return dt.datetime.now(tz).date()

def stamp_today():
    return denver_date_today().strftime("%Y%m%d")

def intro_date_str():
    d = denver_date_today()
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.strftime('%Y')}"

def fetch_headlines(limit_total=12):
    items = []
    for url in SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:6]:
                title = (getattr(e, "title", "") or "").strip()
                link = (getattr(e, "link", "") or "").strip()
                if title:
                    items.append(f"- {title} ({link})")
        except Exception:
            pass
        if len(items) >= limit_total:
            break
    return "\n".join(items[:limit_total])

def fail(msg: str):
    print(msg, file=sys.stderr)
    sys.exit(1)

# ========= OpenAI call (structured) =========

def openai_structured_brief(api_key: str, user_prompt: str) -> dict:
    """
    Returns:
    {
      "sections": [
        {"title": "NEW PRODUCTS & CAPABILITIES", "paragraphs": [{"text":"...", "sources":[1,2]}]},
        ...
      ],
      "footnotes": [{"id":1, "title":"...", "url":"https://..."}]
    }
    """
    client = OpenAI(api_key=api_key)

    system_msg = (
        "You are a senior strategic AI analyst preparing a weekly 4–5 minute executive audio brief. "
        "Audience: executives, strategy consultants, AI adoption leads. "
        "Tone: professional, concise, specific, no hype. "
        "Return ONLY valid JSON. DO NOT include markdown code fences or any text outside the JSON object."
    )

    structure_spec = """
CRITICAL: Your response must be a JSON object with this EXACT structure:

{
  "sections": [
    {
      "title": "NEW PRODUCTS & CAPABILITIES",
      "paragraphs": [
        {"text": "First paragraph text here.", "sources": [1, 2]},
        {"text": "Second paragraph text here.", "sources": [3]}
      ]
    },
    {
      "title": "STRATEGIC BUSINESS IMPACT",
      "paragraphs": [
        {"text": "Paragraph text.", "sources": [1]}
      ]
    },
    {
      "title": "IMPLEMENTATION OPPORTUNITIES",
      "paragraphs": [
        {"text": "Paragraph text.", "sources": [2]}
      ]
    },
    {
      "title": "MARKET DYNAMICS",
      "paragraphs": [
        {"text": "Paragraph text.", "sources": []}
      ]
    },
    {
      "title": "TALENT MARKET SHIFTS",
      "paragraphs": [
        {"text": "Paragraph text.", "sources": [3]}
      ]
    }
  ],
  "footnotes": [
    {"id": 1, "title": "Article Title", "url": "https://example.com/article"},
    {"id": 2, "title": "Another Title", "url": "https://example.com/other"},
    {"id": 3, "title": "Third Source", "url": "https://example.com/third"}
  ]
}

Rules:
- "sections" must be an ARRAY of objects
- Each section object must have "title" (string) and "paragraphs" (array)
- Each paragraph must be an object with "text" (string) and "sources" (array of integers)
- Use 1-3 paragraphs per section
- Keep sentences short (2-3 per paragraph)
- "sources" array contains integer IDs matching footnotes
- No URLs in paragraph text
- "footnotes" is an array of objects with "id" (integer), "title" (string), "url" (string)
"""

    headlines = fetch_headlines()

    user_msg = f"""
Create a {int(TARGET_MIN*160)}-word executive brief for {intro_date_str()}.

Start spoken content with: "Hello, here is your weekly update for {intro_date_str()}"

Optional context (use if relevant):
{headlines}

Additional guidance:
{user_prompt}

Remember: Return ONLY the JSON object. No markdown, no code fences, no explanatory text.
""".strip()

    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": structure_spec},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=2000,
    )

    content = resp.choices[0].message.content.strip()
    
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Top-level is not an object")
        
        # Validate structure
        sections = data.get("sections")
        if not isinstance(sections, list):
            # Handle if OpenAI returned dict instead of array
            if isinstance(sections, dict):
                # Convert {"TITLE": [paragraphs]} to [{"title": "TITLE", "paragraphs": [...]}]
                sections = [{"title": k, "paragraphs": v} for k, v in sections.items()]
                data["sections"] = sections
            else:
                data["sections"] = []
        
        data.setdefault("footnotes", [])
        
        return data
        
    except Exception as e:
        print(f"ERROR parsing OpenAI response: {e}", file=sys.stderr)
        print(f"Response content: {content[:500]}", file=sys.stderr)
        return {
            "sections": [{"title": "Brief", "paragraphs": [{"text": content, "sources": []}]}],
            "footnotes": [],
        }

# ========= Flattener for TTS =========

def flatten_for_voice(sections):
    """Join all paragraph texts into spoken script."""
    parts = [f"Hello, here is your weekly update for {intro_date_str()}"]

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        
        paragraphs = sec.get("paragraphs", [])
        if not isinstance(paragraphs, list):
            continue
        
        for para in paragraphs:
            if isinstance(para, dict):
                text = (para.get("text") or "").strip()
                if text:
                    parts.append(text)
            elif isinstance(para, str):
                text = para.strip()
                if text:
                    parts.append(text)
    
    return "\n\n".join(parts).strip()

# ========= ElevenLabs TTS =========

def elevenlabs_tts(api_key: str, voice_id: str, text: str, out_mp3: Path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {
        "model_id": MODEL_TTS,
        "text": text,
        "voice_settings": {
            "stability": STABILITY,
            "similarity_boost": SIMILARITY,
            "style": STYLE,
            "use_speaker_boost": SPEAKER_BOOST,
        },
    }
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        fail(f"ElevenLabs TTS error {r.status_code}: {r.text[:500]}")
    out_mp3.write_bytes(r.content)

# ========= Main =========

def main():
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        fail("Missing OPENAI_API_KEY in env.")

    el_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not el_key:
        fail("Missing ELEVENLABS_API_KEY in env.")

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not voice_id:
        voice_id = VOICE_ID_MAP.get(VOICE_NAME, "").strip()
    if not voice_id:
        fail("No ELEVENLABS_VOICE_ID provided.")

    brief_spec = (
        "Create a weekly AI executive briefing for operators. "
        "Keep the signal high, specific, and immediately useful. "
        "Avoid filler and speculation. Do not read source attributions on air."
    )

    data = openai_structured_brief(api_key, brief_spec)
    sections = data.get("sections", [])
    footnotes = data.get("footnotes", [])

    spoken = flatten_for_voice(sections)
    if not spoken:
        fail("Empty spoken script after flattening.")

    AUDIO_DIR.mkdir(exist_ok=True)

    base = f"ai_news_{stamp_today()}"
    mp3_path = AUDIO_DIR / f"{base}.mp3"
    json_path = AUDIO_DIR / f"{base}.json"
    txt_path  = AUDIO_DIR / f"{base}.txt"

    elevenlabs_tts(el_key, voice_id, spoken, mp3_path)

    json_path.write_text(json.dumps({"sections": sections, "footnotes": footnotes}, indent=2), encoding="utf-8")

    lines = [spoken]
    if footnotes:
        lines.append("")
        lines.append("---")
        lines.append("Sources:")
        for f in footnotes:
            try:
                iid = f.get("id")
                ttl = (f.get("title") or "").strip()
                url = (f.get("url") or "").strip()
                if not url:
                    continue
                label = f"[{iid}]" if iid is not None else "-"
                if ttl:
                    lines.append(f"{label} {ttl} — {url}")
                else:
                    lines.append(f"{label} {url}")
            except Exception:
                pass
    txt_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {mp3_path.name}, {json_path.name}, {txt_path.name}")

if __name__ == "__main__":
    main()
