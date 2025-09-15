#!/usr/bin/env python3
import os, sys, json, datetime, re, requests, feedparser
from pathlib import Path

# ===== Settings you can tweak =====
AUDIO_DIR   = "audio"

# Text generation (OpenAI)
MODEL_TEXT  = "gpt-4o-mini"        # for writing the script

# ElevenLabs TTS (we’ll prefer ELEVENLABS_VOICE_ID from env if provided)
VOICE_NAME  = "Hannah"             # friendly name only (used if no env id set)
MODEL_TTS   = "eleven_multilingual_v2"  # v2 multilingual
SPEED       = 1.0                  # 0.9–1.1 are safe; keep 1.0 for neutral pacing
STABILITY   = 0.4                  # 0.0-1.0; lower = more expressive, higher = steadier
SIMILARITY  = 0.8                  # 0.0-1.0; higher = stays “on voice”
STYLE       = 0.3                  # 0.0-1.0; adds emphasis/expressiveness
SPEAKER_BOOST = True

TARGET_MIN  = 4.5                  # 4–5 minutes ≈ 700–900 words

# Optional mapping if you want to hard-code IDs later
VOICE_ID_MAP = {
    "Hannah":    "",   # put a real id here if you prefer hard-coding
    "Aria":      "",
    "Emma":      "",
    "Charlotte": "",
}

# Light headline sources (optional context)
SOURCES = [
  "https://www.theverge.com/rss/index.xml",
  "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
  "https://www.marktechpost.com/feed/",
]

# ===== Helpers =====
def denver_date_today():
    # Workflow cron handles timing; we keep date display consistent
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
            f = feedparser.parse(url)
            for e in f.entries[:5]:
                t, l = e.get("title","").strip(), e.get("link","").strip()
                if t and l:
                    items.append(f"- {t} ({l})")
        except Exception:
            pass
    return "\n".join(items[:12])

def openai_chat(api_key, model, messages):
    r = requests.post("https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps({"model": model, "messages": messages, "temperature": 0.7})
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def elevenlabs_tts(api_key, voice_id, text, out_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    payload = {
        "model_id": MODEL_TTS,
        "text": text,
        "voice_settings": {
            "stability": STABILITY,
            "similarity_boost": SIMILARITY,
            "style": STYLE,
            "use_speaker_boost": SPEAKER_BOOST
        },
        "optimize_streaming_latency": 1,
        "output_format": "mp3_44100_128"
        # Some plans support speaking rate; if yours does, uncomment:
        # ,"speaking_rate": SPEED
    }
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    with requests.post(url, headers=headers, data=json.dumps(payload), stream=True) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

def main():
    openai_key = os.environ.get("OPENAI_API_KEY")
    el_key     = os.environ.get("ELEVENLABS_API_KEY")
    if not openai_key:
        print("Missing OPENAI_API_KEY", file=sys.stderr); sys.exit(1)
    if not el_key:
        print("Missing ELEVENLABS_API_KEY", file=sys.stderr); sys.exit(1)

    # Voice ID resolution (env wins; else fallback map)
    env_voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
    if env_voice_id:
        voice_id = env_voice_id
    else:
        vid = VOICE_ID_MAP.get(VOICE_NAME, "")
        if not vid:
            print("No ELEVENLABS_VOICE_ID in env and VOICE_ID_MAP entry is empty.", file=sys.stderr)
            sys.exit(1)
        voice_id = vid

    # Build your brief spec (4–5 minutes, exact intro, 5 sections)
    brief_spec = f"""You are a strategic AI analyst preparing a weekly briefing for business executives,
strategy consultants, AI adoption strategists, and solutions consultants.

Create a 4–5 minute spoken summary (~700–900 words) of the week's AI developments with this structure:

Intro (one line, exactly):
"AI Updates for {intro_date_str()}."

Then proceed through these FIVE sections with short, spoken headers and tight, actionable content.

1) NEW PRODUCTS & CAPABILITIES:
   - What launched, key features, availability timeline, practical business applications.

2) STRATEGIC BUSINESS IMPACT:
   - How these developments affect enterprise strategy and competitive positioning.

3) IMPLEMENTATION OPPORTUNITIES:
   - Specific ways companies are using AI for efficiency and profitability (include concrete examples).

4) MARKET DYNAMICS:
   - Funding, partnerships, regulatory changes affecting AI adoption, and major risks/privacy concerns.

5) TALENT MARKET SHIFTS:
   - AI hiring trends, skill gaps, and where demand is moving.

Tone: professional but conversational for audio. Focus on actionable intelligence, not hype.
Do NOT read author names or citations aloud. You may say names of tools, companies, or people if it aids specificity.
Finish with: "That’s your AI Executive Brief for the week."
"""

    headlines = fetch_headlines()
    user = f"""{brief_spec}

Optional context to consider (only if genuinely useful; otherwise ignore):
{headlines}
"""

    script = openai_chat(openai_key, MODEL_TEXT, [
        {"role":"system","content":"You are a senior analyst. Write concise, factual, audio-friendly copy with strong signal and no fluff."},
        {"role":"user","content": user}
    ]).strip()

    Path(AUDIO_DIR).mkdir(exist_ok=True)
    fname    = f"ai_news_{monday_stamp()}.mp3"
    mp3_path = Path(AUDIO_DIR)/fname
    txt_path = Path(AUDIO_DIR)/f"{Path(fname).stem}.txt"

    elevenlabs_tts(el_key, voice_id, script, mp3_path)
    txt_path.write_text(script, encoding="utf-8")
    print(f"Wrote {mp3_path} and {txt_path} using ElevenLabs voice id '{voice_id}'")

if __name__ == "__main__":
    main()
