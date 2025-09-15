#!/usr/bin/env python3
import os, sys, json, datetime, re, requests, feedparser
from pathlib import Path

# ===== Settings you can tweak =====
AUDIO_DIR = "audio"

# Text generation (OpenAI)
MODEL_TEXT = "gpt-4o-mini"          # for writing the scripts

# ElevenLabs TTS (audio uses the clean/no-citations version)
VOICE_NAME = "Hannah"               # friendly name (used only if no env id set)
MODEL_TTS = "eleven_multilingual_v2"
SPEED = 1.0
STABILITY = 0.3
SIMILARITY = 0.8
STYLE = 0.2
SPEAKER_BOOST = True

TARGET_MIN = 4.5                    # 4–5 minutes ≈ 700–900 words

# Optional mapping if you want hard-code IDs later
VOICE_ID_MAP = {
    "Hannah": "",   # put real id here if you prefer hard-coding
}

# Light headline sources (contextual, optional)
SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
]

# ---------- Helpers ----------
def denver_date_today():
    # Keep display stable vs cron TZ
    denver = datetime.timezone(datetime.timedelta(hours=-6))
    return datetime.datetime.now(datetime.timezone.utc).astimezone(denver).date()

def monday_stamp():
    d = denver_date_today()
    monday = d - datetime.timedelta(days=d.weekday())
    return monday.strftime("%Y%m%d")

def intro_date_str():
    d = denver_date_today()
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.strftime('%Y')}"

def fetch_headlines():
    items = []
    for url in SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:10]:
                title = (getattr(e, "title", "") or "").strip()
                link = (getattr(e, "link", "") or "").strip()
                if title and link:
                    items.append(f"- {title}  ({link})")
        except Exception:
            pass
    return "\n".join(items[:30])

# ---------- OpenAI ----------
def openai_chat(api_key, model, messages):
    import openai
    openai.api_key = api_key
    # Classic Chat Completions
    resp = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0.4,
        max_tokens=1400,
    )
    return resp.choices[0].message["content"]

# ---------- ElevenLabs ----------
def eleven_tts(api_key, model, voice, text, out_path):
    # Prefer env id, else map, else friendly name
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    if not voice_id:
        voice_id = VOICE_ID_MAP.get(voice, "") or voice

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model,
        "voice_settings": {
            "stability": STABILITY,
            "similarity_boost": SIMILARITY,
            "style": STYLE,
            "use_speaker_boost": SPEAKER_BOOST,
        },
        "voice": voice,
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    r.raise_for_status()
    Path(out_path).write_bytes(r.content)

# ---------- Main ----------
def main():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("Missing OPENAI_API_KEY", file=sys.stderr); sys.exit(1)

    tts_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not tts_key:
        print("Missing ELEVENLABS_API_KEY", file=sys.stderr); sys.exit(1)

    # Verbatim category framing you requested
    categories_block = (
        "1) NEW PRODUCTS & CAPABILITIES — launches, key features, availability timeline, practical business use-cases\n"
        "2) STRATEGIC BUSINESS IMPACT — implications for enterprise strategy and competitive positioning\n"
        "3) IMPLEMENTATION OPPORTUNITIES — concrete ways companies use AI for efficiency/profitability\n"
        "4) MARKET DYNAMICS — funding, partnerships, regulatory moves, risks & privacy concerns\n"
        "5) TALENT MARKET SHIFTS — hiring trends, skill gaps, where demand is moving"
    )

    date_str = intro_date_str()
    brief_spec = f"""AI Updates for {date_str}.

You are a strategic AI analyst preparing a weekly briefing for business executives, strategy consultants, AI adoption strategists, and solutions consultants.
Create a 4–5 minute spoken summary of the week's AI developments that moves through these sections in order:

{categories_block}

Keep it professional but conversational for audio. Focus on actionable intelligence, not hype. Begin right after the line “AI Updates for …” and progress through the five sections with clear signposts.
"""

    headlines = fetch_headlines()

    # --- AUDIO VERSION (no citations anywhere) ---
    system_audio = {
        "role": "system",
        "content": (
            "You are a senior analyst. Write concise, factual, audio-friendly copy with strong signal and clear structure. "
            "Absolutely do NOT include citations, URLs, square brackets, footnotes, or markers. "
            "Avoid saying source names aloud unless they materially help clarity. "
            "Target ~750–900 words for 4–5 minutes."
        ),
    }
    user_audio = {
        "role": "user",
        "content": f"""{brief_spec}

Optional context to consider (only if genuinely useful; otherwise ignore):
{headlines}
""",
    }

    # --- TRANSCRIPT VERSION (with end-of-text footnotes) ---
    system_transcript = {
        "role": "system",
        "content": (
            "You are a senior analyst. Produce the same briefing text, but include footnote-style citations. "
            "In the body, place compact numeric markers like [^1], [^2] after the relevant sentence (no URLs in body). "
            "At the very end, add a section titled 'References' with one bullet per footnote in order. "
            "Each bullet should be: [^n] Title — Publisher or Org — short URL (use the public/permalink version; shorten if the site provides a short form). "
            "Only cite material necessary to support key claims; avoid over-citation."
        ),
    }
    user_transcript = user_audio  # same spec/context

    audio_script = openai_chat(api_key, MODEL_TEXT, [system_audio, user_audio]).strip()
    transcript_script = openai_chat(api_key, MODEL_TEXT, [system_transcript, user_transcript]).strip()

    # Paths
    Path(AUDIO_DIR).mkdir(exist_ok=True)
    fname = f"ai_news_{monday_stamp()}.mp3"
    mp3_path = Path(AUDIO_DIR) / fname
    txt_path = Path(AUDIO_DIR) / f"{Path(fname).stem}.txt"

    # Generate
    eleven_tts(tts_key, MODEL_TTS, VOICE_NAME, audio_script, mp3_path)
    txt_path.write_text(transcript_script, encoding="utf-8")

    print(f"Wrote {mp3_path} and {txt_path}")
    print("\n--- AUDIO SCRIPT (first 400 chars) ---\n")
    print(audio_script[:400])

if __name__ == "__main__":
    main()
