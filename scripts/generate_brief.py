#!/usr/bin/env python3
import os, sys, json, datetime, re, requests, feedparser
from pathlib import Path
from openai import OpenAI

AUDIO_DIR = "audio"
MODEL_TEXT = "gpt-4o-mini"
TARGET_MIN = 4.5

# ElevenLabs TTS
VOICE_NAME = "Hannah"
MODEL_TTS = "eleven_multilingual_v2"
SPEED = 1.0
STABILITY = 0.3
SIMILARITY = 0.8
STYLE = 0.1
SPEAKER_BOOST = True

VOICE_ID_MAP = {
    # "Hannah": "xxxxxxxxxxxxxxxxxxxxxxxx",
}

SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
]

def denver_date_today():
    import pytz
    mountain_tz = pytz.timezone('America/Denver')
    return datetime.datetime.now(mountain_tz).date()

def monday_stamp():
    d = denver_date_today()
    return d.strftime("%Y%m%d")

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

def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def openai_structured_brief(api_key: str, user_prompt: str) -> dict:
    """
    Preferred JSON:
    {
      "sentences": [ {"text":"...", "sources":[1,3]}, ... ],
      "footnotes": [ {"id":1, "title":"...", "url":"..."} ]
    }
    Fallback JSON (legacy):
    { "spoken":"...", "footnotes":[...] }
    """
    client = OpenAI(api_key=api_key)

    system_msg = (
        "You are a senior strategic AI analyst preparing a weekly 4–5 minute executive audio brief. "
        "Audience: business executives, strategy consultants, AI adoption leads, and solutions consultants. "
        "Tone: professional and concise for audio. Focus on actionable intelligence. "
        "Return JSON with sentence-level attributions:\n"
        "{ 'sentences': [{'text':'...','sources':[1,2]}, ...], 'footnotes': [{'id':1,'title':'...','url':'...'}] }\n"
        "The first sentence MUST be exactly: "
        f"'Hello, here is your weekly update for {intro_date_str()}' "
        "Do not include URLs or inline brackets inside sentences."
    )

    categories = (
        "1) NEW PRODUCTS & CAPABILITIES — launches, features, availability, practical use-cases\n"
        "2) STRATEGIC BUSINESS IMPACT — implications for enterprise strategy and competition\n"
        "3) IMPLEMENTATION OPPORTUNITIES — concrete efficiency and profit plays\n"
        "4) MARKET DYNAMICS — funding, partnerships, regulation, risks and privacy\n"
        "5) TALENT MARKET SHIFTS — hiring trends and skill gaps\n"
    )
    headlines = fetch_headlines()
    user_msg = f"""
Write ~{int(TARGET_MIN*160)} words (~{TARGET_MIN:0.1f}–{TARGET_MIN+0.7:0.1f} min) across the five categories, in that order.

Rules:
- No URLs or inline citations inside sentences.
- Put sources only in footnotes with exact links.
- Provide sentence-level 'sources' ids array per sentence (empty array if none).

Optional recent headlines (use only if helpful):
{headlines}

Policy/intent:
{user_prompt}
""".strip()

    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[{"role":"system","content":system_msg},{"role":"user","content":user_msg}],
        temperature=0.4,
        max_tokens=1700,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        assert isinstance(data, dict)
        return data
    except Exception:
        return {"spoken": content, "footnotes": []}

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
    headers = {"xi-api-key": api_key, "accept": "audio/mpeg", "content-type": "application/json"}
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code != 200:
        fail(f"ElevenLabs TTS error {r.status_code}: {r.text[:500]}")
    out_mp3.write_bytes(r.content)

def main():
    api_key = os.environ.get("OPENAI_API_KEY","").strip()
    if not api_key: fail("Missing OPENAI_API_KEY.")
    el_key  = os.environ.get("ELEVENLABS_API_KEY","").strip()
    if not el_key:  fail("Missing ELEVENLABS_API_KEY.")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID","").strip() or VOICE_ID_MAP.get(VOICE_NAME,"").strip()
    if not voice_id: fail("Missing ELEVENLABS_VOICE_ID.")

    brief_spec = ("Create a weekly AI executive briefing for operators. Keep it concise and useful. "
                  "Avoid filler and do not read source attributions aloud.")

    data = openai_structured_brief(api_key, brief_spec)

    sentences = data.get("sentences")
    footnotes = data.get("footnotes", [])

    if sentences and isinstance(sentences, list):
        spoken_text = " ".join([s.get("text","").strip() for s in sentences if s.get("text")])
        structured = {"sentences": sentences, "footnotes": footnotes}
    else:
        # Legacy fallback
        spoken_text = (data.get("spoken") or "").strip()
        if not spoken_text:
            fail("OpenAI returned no spoken content.")
        structured = {
            "sentences": [{"text": t.strip(), "sources": []}
                          for t in re.split(r'(?<=[.!?])\s+', spoken_text) if t.strip()],
            "footnotes": footnotes
        }

    Path(AUDIO_DIR).mkdir(exist_ok=True)
    base = f"ai_news_{monday_stamp()}"
    mp3_path = Path(AUDIO_DIR)/f"{base}.mp3"
    json_path = Path(AUDIO_DIR)/f"{base}.json"
    txt_path  = Path(AUDIO_DIR)/f"{base}.txt"

    # TTS from spoken_text
    elevenlabs_tts(el_key, voice_id, spoken_text, mp3_path)

    # Keep simple .txt with Sources block for continuity
    src_block = ""
    if footnotes:
        lines = ["", "---", "Sources:"]
        for item in footnotes:
            iid = item.get("id"); ttl = (item.get("title") or "").strip(); url = (item.get("url") or "").strip()
            if not url: continue
            label = f"[{iid}]" if iid else "- "
            lines.append(f"{label} {ttl} --- {url}" if ttl else f"{label} {url}")
        src_block = "\n".join(lines)
    txt_path.write_text(spoken_text + ("\n"+src_block if src_block else ""), encoding="utf-8")

    # Save structured JSON for compose_transcript.py
    json_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {mp3_path}, {txt_path}, and {json_path}")

if __name__ == "__main__":
    main()
