#!/usr/bin/env python3
import os, sys, json, datetime, re, requests, feedparser
from pathlib import Path

# ----- Settings (edit if you like) -----
AUDIO_DIR  = "audio"
VOICE      = "alloy"            # OpenAI TTS voice
MODEL_TEXT = "gpt-4o-mini"      # for writing the script
MODEL_TTS  = "gpt-4o-mini-tts"  # for speech
TARGET_MIN = 4.5                # 4–5 minutes ≈ 700–900 words

# Light headline sources to give the model weekly context (optional; keep or expand)
SOURCES = [
  "https://www.theverge.com/rss/index.xml",
  "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
  "https://www.marktechpost.com/feed/",
]

# ---------- Helpers ----------
def denver_date_today():
    # Use a fixed MST base; the workflow time-gates at 08:00 America/Denver,
    # so date correctness is preserved regardless of DST offset.
    denver = datetime.timezone(datetime.timedelta(hours=-6))
    return datetime.datetime.now(datetime.timezone.utc).astimezone(denver).date()

def monday_stamp():
    d = denver_date_today()
    monday = d - datetime.timedelta(days=d.weekday())
    return monday.strftime("%Y%m%d")

def intro_date_str():
    d = denver_date_today()
    # e.g., "Monday, September 15, 2025"
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

def openai_tts(api_key, model, voice, text, out_path):
    r = requests.post("https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps({"model": model, "voice": voice, "input": text, "format": "mp3"})
    )
    r.raise_for_status()
    out_path.write_bytes(r.content)

# ---------- Main ----------
def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Missing OPENAI_API_KEY", file=sys.stderr); sys.exit(1)

    # Build the exact brief spec you requested
    brief_spec = f"""You are a strategic AI analyst preparing a weekly briefing for business executives,
strategy consultants, AI adoption strategists, and solutions consultants.

Create a **4–5 minute** spoken summary (~700–900 words) of the week's AI developments with this structure:

Intro (one line, exactly):
"AI Updates for {intro_date_str()}."

Then proceed through these FIVE sections with short, spoken headers and tight, actionable content.
Do not include any filler. Prioritize specificity, names, and practical implications.

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

Tone: professional but conversational for audio. Focus on **actionable intelligence**, not hype.
Do NOT read author names or citations aloud. You may say names of tools, companies, or people if it aids specificity.
Finish with a single-line closer: "That’s your AI Executive Brief for the week."
"""

    headlines = fetch_headlines()
    user = f"""{brief_spec}

Optional context to consider (only if genuinely useful; otherwise ignore):
{headlines}
"""

    script = openai_chat(api_key, MODEL_TEXT, [
        {"role":"system","content":"You are a senior analyst. Write concise, factual, audio-friendly copy with strong signal and no fluff."},
        {"role":"user","content": user}
    ]).strip()

    Path(AUDIO_DIR).mkdir(exist_ok=True)
    fname = f"ai_news_{monday_stamp()}.mp3"
    mp3_path = Path(AUDIO_DIR)/fname
    txt_path = Path(AUDIO_DIR)/f"{Path(fname).stem}.txt"

    openai_tts(api_key, MODEL_TTS, VOICE, script, mp3_path)
    txt_path.write_text(script, encoding="utf-8")
    print(f"Wrote {mp3_path} and {txt_path}")

if __name__ == "__main__":
    main()
