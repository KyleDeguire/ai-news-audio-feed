#!/usr/bin/env python3

import os, sys, json, datetime, re, requests, feedparser
from pathlib import Path
from openai import OpenAI

# ===== Settings you can tweak =====

AUDIO_DIR = "audio"

# OpenAI models
MODEL_TEXT = "gpt-4o-mini"  # writing the brief (JSON output)
TARGET_MIN = 4.5  # 4--5 minutes ~= ~750--900 words

# ElevenLabs TTS (Option A)
VOICE_NAME = "Hannah"  # friendly label (only used if no env voice id)
MODEL_TTS = "eleven_multilingual_v2"
SPEED = 1.0
STABILITY = 0.3  # 0..1 lower = more expressive
SIMILARITY = 0.8  # 0..1 higher = stays "on voice"
STYLE = 0.1  # 0..1 adds emphasis/expressiveness
SPEAKER_BOOST = True

# Optional mapping if you want to hard-code IDs (fill these if you prefer)
VOICE_ID_MAP = {
    # "Hannah": "xxxxxxxxxxxxxxxxxxxxxxxx",  # <- put your Hannah voice_id here if you want
}

# Light headline sources to give the model weekly context (optional)
SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
]

# ===== Helpers =====

def denver_date_today():
    """Get current date in Mountain Time (UTC-7 for DST, UTC-6 for standard)"""
    # September is DST, so UTC-7
    import pytz
    mountain_tz = pytz.timezone('America/Denver')
    now_mountain = datetime.datetime.now(mountain_tz)
    return now_mountain.date()

def monday_stamp():
    """Return YYYYMMDD for today's date (not Monday of week)"""
    d = denver_date_today()
    return d.strftime("%Y%m%d")

def intro_date_str():
    d = denver_date_today()
    # e.g., "Monday, September 16, 2025"
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.strftime('%Y')}"

def fetch_headlines(limit_total=12):
    """Very light 'ambient context' for the model. Totally optional."""
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

def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

# ===== OpenAI (new client) =====

def openai_structured_brief(api_key: str, user_prompt: str) -> dict:
    """
    Ask the model to return JSON:
    { "spoken": "<no-citation voice script>",
      "footnotes": [ { "id": 1, "title": "...", "url": "https://..." }, ... ] }
    """
    client = OpenAI(api_key=api_key)
    
    system_msg = (
        "You are a senior strategic AI analyst preparing a weekly 4--5 minute executive audio brief. "
        "Audience: business executives, strategy consultants, AI adoption leads, and solutions consultants. "
        "Tone: professional but conversational for audio. Focus on actionable intelligence, not hype. "
        "DO NOT read citations aloud. Produce clean plain text for voice (no brackets, no URLs, no inline citations). "
        "Return JSON with two fields:\n"
        " - spoken: the full spoken script only (no citations or URLs)\n"
        " - footnotes: an array of {id, title, url} with exact source links used to inform your analysis\n"
        "Spoken script must begin with the line: "
        f'"Hello, here is your weekly update for {intro_date_str()}" and then immediately cover the five categories in order.'
    )
    
    # Your exact category framing (kept verbatim)
    categories = (
        "1) NEW PRODUCTS & CAPABILITIES --- launches, key features, availability timeline, practical business use-cases\n"
        "2) STRATEGIC BUSINESS IMPACT --- implications for enterprise strategy and competitive positioning\n"
        "3) IMPLEMENTATION OPPORTUNITIES --- concrete ways companies use AI for efficiency/profitability\n"
        "4) MARKET DYNAMICS --- funding, partnerships, regulatory moves, risks & privacy concerns\n"
        "5) TALENT MARKET SHIFTS --- hiring trends, skill gaps, where demand is moving\n"
    )
    
    # Optional context
    headlines = fetch_headlines()
    
    user_msg = f"""
Write a concise ~{int(TARGET_MIN*160)}-word audio brief (~{TARGET_MIN:0.1f}--{TARGET_MIN+0.7:0.1f} minutes).

Follow exactly this outline (use on-air friendly transitions and short sentences):

{categories}

Constraints:
- Keep it specific and useful for operators (avoid hype).
- You may name tools, companies, or people for specificity.
- DO NOT include any URLs or bracketed citations in the spoken script.
- Put sources ONLY in the footnotes array as JSON with exact links.

Optional recent headlines to consider (use only if genuinely useful):

{headlines}

User prompt / policy notes for this week:

{user_prompt}
""".strip()
    
    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
        max_tokens=1600,
    )
    
    content = resp.choices[0].message.content.strip()
    
    try:
        data = json.loads(content)
        if not isinstance(data, dict) or "spoken" not in data or "footnotes" not in data:
            raise ValueError("JSON missing required keys.")
        return data
    except Exception as e:
        # Fallback: treat whole thing as spoken if JSON parsing fails
        return {"spoken": content, "footnotes": []}

# ===== ElevenLabs TTS =====

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
        }
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

# ===== Main =====

def main():
    # --- Secrets
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        fail("Missing OPENAI_API_KEY in env.")
    
    el_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not el_key:
        fail("Missing ELEVENLABS_API_KEY in env.")
    
    # Resolve voice id
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if not voice_id:
        voice_id = VOICE_ID_MAP.get(VOICE_NAME, "").strip()
    if not voice_id:
        fail("No ELEVENLABS_VOICE_ID in env and VOICE_ID_MAP entry is empty. "
             "Add ELEVENLABS_VOICE_ID secret (preferred) or fill VOICE_ID_MAP[Hannah].")
    
    # --- Build the user policy/spec (kept verbatim & extendable)
    brief_spec = (
        "Create a weekly AI executive briefing for operators. "
        "Keep the signal high, concise and immediately useful for decisions. "
        "Avoid filler, avoid speculation, and avoid reading any source attributions on air."
    )
    
    # --- Get structured result from OpenAI (spoken + footnotes)
    data = openai_structured_brief(api_key, brief_spec)
    spoken = data.get("spoken", "").strip()
    footnotes = data.get("footnotes", [])
    
    if not spoken:
        fail("OpenAI returned an empty spoken script.")
    
    # --- Assemble transcript with footnotes (links)
    foot_block = ""
    if footnotes:
        lines = ["", "---", "Sources:"]
        for item in footnotes:
            try:
                iid = item.get("id")
                ttl = (item.get("title") or "").strip()
                url = (item.get("url") or "").strip()
                # Extremely shortener is avoided here; keep direct links for reliability.
                if not url:
                    continue
                label = f"[{iid}]" if iid else "- "
                if ttl:
                    lines.append(f"{label} {ttl} --- {url}")
                else:
                    lines.append(f"{label} {url}")
            except Exception:
                pass
        foot_block = "\n".join(lines)
    
    transcript_text = spoken + ("\n" + foot_block if foot_block else "")
    
    # --- Save audio + transcript
    Path(AUDIO_DIR).mkdir(exist_ok=True)
    fname_base = f"ai_news_{monday_stamp()}"
    mp3_path = Path(AUDIO_DIR) / f"{fname_base}.mp3"
    txt_path = Path(AUDIO_DIR) / f"{fname_base}.txt"
    
    # TTS from the SPOKEN version (no citations)
    elevenlabs_tts(el_key, voice_id, spoken, mp3_path)
    
    # Transcript (with footnotes block)
    txt_path.write_text(transcript_text, encoding="utf-8")
    
    print(f"Wrote {mp3_path} and {txt_path}")

if __name__ == "__main__":
    main()
