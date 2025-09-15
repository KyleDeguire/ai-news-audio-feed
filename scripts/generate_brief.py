#!/usr/bin/env python3
import os, sys, json, datetime, re, requests, feedparser
from pathlib import Path

# ===== Settings you can tweak =====
AUDIO_DIR = "audio"

# Text generation (OpenAI)
MODEL_TEXT = "gpt-4o-mini"     # for writing the script

# ElevenLabs TTS (we’ll prefer ELEVENLABS_VOICE_ID from env if provided)
VOICE_NAME  = "Hannah"         # friendly name (used only if no env id set)
MODEL_TTS   = "eleven_multilingual_v2"  # v2 multilingual
SPEED       = 1.0              # 0.9–1.1 are safe
STABILITY   = 0.8              # 0.0–1.0 lower = more expressive
SIMILARITY  = 0.8              # 0.0–1.0 higher = more on-voice
STYLE       = 0.0              # 0.0–1.0 adds emphasis/expressiveness
SPEAKER_BOOST = True

TARGET_MIN = 4.5               # 4–5 minutes ~700–900 words

# Optional mapping if you want to hard-code IDs
VOICE_ID_MAP = {
    "Hannah":    "YOUR-HANNAH-VOICE-ID-HERE",
    "Aria":      "",
    "Emma":      "",
    "Charlotte": "",
}

# === Resolve which voice ID to use ===
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
if not VOICE_ID and VOICE_NAME in VOICE_ID_MAP:
    VOICE_ID = VOICE_ID_MAP[VOICE_NAME].strip()
if not VOICE_ID:
    raise SystemExit("❌ No ELEVENLABS_VOICE_ID set (env or VOICE_ID_MAP). Please configure one.")

# ===== Light headline sources (optional context) =====
SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
]

# ===== Helpers =====
def denver_date_today():
    denver = datetime.timezone(datetime.timedelta(hours=-6))
    return datetime.datetime.now(datetime.timezone.utc).astimezone(denver).date()

def monday_stamp():
    today = denver_date_today()
    monday = today - datetime.timedelta(days=today.weekday())
    return monday.strftime("%Y%m%d")

def intro_date_str():
    today = denver_date_today()
    return today.strftime("%B %d, %Y")

# ===== OpenAI wrappers =====
def openai_chat(api_key, model, messages):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.6,
        max_tokens=2000,
    )
    return resp.choices[0].message.content
def openai_tts_elevenlabs(api_key, voice_id, text, path_out):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    payload = {
        "text": text,
        "model_id": MODEL_TTS,
        "voice_settings": {
            "stability": STABILITY,
            "similarity_boost": SIMILARITY,
            "style": STYLE,
            "use_speaker_boost": SPEAKER_BOOST,
        },
    }
    with requests.post(url, headers=headers, json=payload, stream=True) as r:
        r.raise_for_status()
        with open(path_out, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

# ===== Headline fetch (optional) =====
def fetch_headlines():
    out = []
    for url in SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:3]:
                out.append(f"- {e.title}")
        except Exception:
            pass
    return "\n".join(out)

# ===== Main =====
def main():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("❌ Missing OPENAI_API_KEY in env.")

    brief_spec = f"""
You are a strategic AI analyst preparing a weekly briefing for business executives, strategy consultants,
AI adoption strategists, and solutions consultants. Create a 4–5 minute spoken summary of the week's AI
developments. Start with: "AI Updates for {intro_date_str()}." Then cover the five sections:

1) NEW PRODUCTS & CAPABILITIES — launches, key features, availability timeline, practical business use-cases
2) STRATEGIC BUSINESS IMPACT — implications for enterprise strategy and competitive positioning
3) IMPLEMENTATION OPPORTUNITIES — concrete ways companies use AI for efficiency/profitability
4) MARKET DYNAMICS — funding, partnerships, regulatory moves, risks & privacy concerns
5) TALENT MARKET SHIFTS — hiring trends, skill gaps, where demand is moving

Tone: professional but conversational for audio. Focus on actionable intelligence, not hype.

Important formatting:
- Write the narration as normal paragraphs (no numbered citations in-line).
- After the narration, add a section exactly titled: "Sources:" on its own line.
- Under "Sources:", include a numbered list of 5–12 items. Each item should be:
  Site / Publisher — Article Title — URL
- Do NOT include the "Sources" section in the spoken narration; it's only for the transcript readers.

If a section is light for the week, keep it tight. Aim for ~700–900 words total.
"""

    headlines = fetch_headlines()
    user_prompt = f"""{brief_spec}

Optional context to consider (use only if helpful; otherwise ignore):
{headlines}
"""

    # --- Generate script with OpenAI
    script_full = openai_chat(api_key, MODEL_TEXT, [
        {"role": "system", "content": "You are a senior analyst. Write concise, factual, audio-friendly copy with strong signal and clear structure."},
        {"role": "user", "content": user_prompt}
    ]).strip()

    # Split narration vs. sources
    split_tok = "\nSources:"
    parts = script_full.split(split_tok, 1)
    narration = parts[0].rstrip()
    sources_blk = (split_tok + parts[1]).strip() if len(parts) > 1 else ""

    Path(AUDIO_DIR).mkdir(exist_ok=True)
    fname = f"ai_news_{monday_stamp()}.mp3"
    mp3_path = Path(AUDIO_DIR) / fname
    txt_path = Path(AUDIO_DIR) / (Path(fname).stem + ".txt")

    # --- Generate MP3 with ElevenLabs (narration only)
    openai_tts_elevenlabs(os.getenv("ELEVENLABS_API_KEY"), VOICE_ID, narration, mp3_path)

    # --- Save transcript with sources
    transcript_to_save = narration + ("\n\n" + sources_blk if sources_blk else "")
    txt_path.write_text(transcript_to_save, encoding="utf-8")

if __name__ == "__main__":
    main()
