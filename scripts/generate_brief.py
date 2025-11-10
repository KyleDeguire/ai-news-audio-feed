#!/usr/bin/env python3
"""
scripts/generate_brief.py

Generates:
  - audio/ai_news_YYYYMMDD.mp3      (spoken script, no citations)
  - audio/ai_news_YYYYMMDD.json     (structured transcript with sources)
  - audio/ai_news_YYYYMMDD.txt      (plain-text transcript + Sources block)

Secrets required (repo → Settings → Secrets and variables → Actions):
  - OPENAI_API_KEY
  - ELEVENLABS_API_KEY
  - ELEVENLABS_VOICE_ID
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

# OpenAI model for drafting the brief
MODEL_TEXT = "gpt-4o-mini"   # concise, reliable for JSON output
TARGET_MIN = 4.5             # ~4–5 minutes

# ElevenLabs TTS
VOICE_NAME = "Hannah"        # fallback label if you ever map names → IDs
MODEL_TTS = "eleven_multilingual_v2"
STABILITY = 0.3
SIMILARITY = 0.8
STYLE = 0.1
SPEAKER_BOOST = True

# Optional hard map if you prefer not to use env ELEVENLABS_VOICE_ID
VOICE_ID_MAP = {
    # "Hannah": "xxxxxxxxxxxxxxxxxxxxxxxx"
}

# Light context feeds (optional, model uses only if helpful)
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
    Ask model to return STRICT JSON with:
    {
      "sections": [
        {
          "title": "NEW PRODUCTS & CAPABILITIES",
          "paragraphs": [
            { "sentences": [ {"text": "...", "sources":[1,2]}, ... ] },
            ...
          ]
        },
        ...
      ],
      "footnotes": [ {"id":1,"title":"...","url":"https://..."}, ... ]
    }
    """
    client = OpenAI(api_key=api_key)

    system_msg = (
        "You are a senior strategic AI analyst preparing a weekly 4–5 minute executive audio brief. "
        "Audience: executives, strategy consultants, AI adoption leads. "
        "Tone: professional, concise, specific, no hype. "
        "Return a STRICT JSON object with keys 'sections' and 'footnotes'. "
        "Sections MUST follow the 5-category outline below and include paragraphs→sentences. "
        "Each sentence may include an optional 'sources' array of integer ids that map to footnotes. "
        "DO NOT put URLs in sentences. Do not include citations in the spoken text."
    )

    outline = (
        "Required sections in this exact order and titling:\n"
        "1) NEW PRODUCTS & CAPABILITIES\n"
        "2) STRATEGIC BUSINESS IMPACT\n"
        "3) IMPLEMENTATION OPPORTUNITIES\n"
        "4) MARKET DYNAMICS\n"
        "5) TALENT MARKET SHIFTS\n"
        "\n"
        "For each section, provide 1–3 paragraphs. For each paragraph, provide 1–3 sentences.\n"
        "Sentence object shape: {\"text\":\"...\", \"sources\":[1,3]} (sources optional).\n"
        "footnotes is an array of {\"id\":<int>, \"title\":\"...\", \"url\":\"https://...\"}."
    )

    headlines = fetch_headlines()

    user_msg = f"""
Spoken brief must begin with:
"Hello, here is your weekly update for {intro_date_str()}"

Length target: ~{int(TARGET_MIN*160)} words total across all sections.

Constraints:
- No URLs or bracketed citations in sentences.
- Keep sentences short and on-air friendly.
- Use sources only via numeric ids in 'sources' per sentence.

Optional recent headlines (use only if useful):
{headlines}

Policy / operator guidance:
{user_prompt}
""".strip()

    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": outline},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=1800,
    )

    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("Top-level is not an object")
        # Ensure required keys exist
        data.setdefault("sections", [])
        data.setdefault("footnotes", [])
        return data
    except Exception:
        # Very defensive fallback so the run never crashes
        return {
            "sections": [
                {
                    "title": "Brief",
                    "paragraphs": [
                        {"sentences": [{"text": content, "sources": []}]}
                    ],
                }
            ],
            "footnotes": [],
        }

# ========= Robust flattener for TTS =========

def flatten_for_voice(sections):
    """
    Join all sentences into an on-air script. Robust to malformed structures:
    - tolerates section/paragraph as str or dict
    - ignores missing keys safely
    """
    parts = [f"Hello, here is your weekly update for {intro_date_str()}"]

    for sec in sections:
        # section can be dict or str
        if isinstance(sec, str):
            # if a stray title string slipped in, skip
            continue
        if not isinstance(sec, dict):
            continue

        paragraphs = sec.get("paragraphs", [])
        if isinstance(paragraphs, str):
            if paragraphs.strip():
                parts.append(paragraphs.strip())
            continue

        if not isinstance(paragraphs, list):
            continue

        for para in paragraphs:
            # paragraph can be dict or str
            if isinstance(para, str):
                if para.strip():
                    parts.append(para.strip())
                continue
            if not isinstance(para, dict):
                continue

            sentences = para.get("sentences", [])
            if isinstance(sentences, str):
                if sentences.strip():
                    parts.append(sentences.strip())
                continue
            if not isinstance(sentences, list):
                continue

            sent_texts = []
            for s in sentences:
                if isinstance(s, dict):
                    t = (s.get("text") or "").strip()
                    if t:
                        sent_texts.append(t)
                elif isinstance(s, str):
                    if s.strip():
                        sent_texts.append(s.strip())

            if sent_texts:
                parts.append(" ".join(sent_texts))

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
    # Secrets
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

    # Operator brief spec (kept short, you can extend any week)
    brief_spec = (
        "Create a weekly AI executive briefing for operators. "
        "Keep the signal high, specific, and immediately useful. "
        "Avoid filler and speculation. Do not read source attributions on air."
    )

    # Call OpenAI for structured JSON
    data = openai_structured_brief(api_key, brief_spec)
    sections = data.get("sections", [])
    footnotes = data.get("footnotes", [])

    # Build spoken script (no citations)
    spoken = flatten_for_voice(sections)
    if not spoken:
        fail("Empty spoken script after flattening.")

    # Ensure out dir
    AUDIO_DIR.mkdir(exist_ok=True)

    base = f"ai_news_{stamp_today()}"
    mp3_path = AUDIO_DIR / f"{base}.mp3"
    json_path = AUDIO_DIR / f"{base}.json"
    txt_path  = AUDIO_DIR / f"{base}.txt"

    # TTS
    elevenlabs_tts(el_key, voice_id, spoken, mp3_path)

    # Save JSON (full structure)
    json_path.write_text(json.dumps({"sections": sections, "footnotes": footnotes}, indent=2), encoding="utf-8")

    # Plain-text transcript (paragraph blocks + Sources)
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
