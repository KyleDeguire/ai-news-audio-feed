#!/usr/bin/env python3
import os, sys, json, datetime, requests, feedparser
from pathlib import Path
from openai import OpenAI

AUDIO_DIR = "audio"

MODEL_TEXT = "gpt-4o-mini"
TARGET_MIN = 4.5

VOICE_NAME = "Hannah"
MODEL_TTS = "eleven_multilingual_v2"
STABILITY = 0.3
SIMILARITY = 0.8
STYLE = 0.1
SPEAKER_BOOST = True

VOICE_ID_MAP = {}

SOURCES_FEEDS = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
]

def denver_date_today():
    import pytz
    tz = pytz.timezone('America/Denver')
    return datetime.datetime.now(tz).date()

def monday_stamp():
    return denver_date_today().strftime("%Y%m%d")

def intro_date_str():
    d = denver_date_today()
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.strftime('%Y')}"

def fetch_headlines(limit_total=12):
    items = []
    for url in SOURCES_FEEDS:
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
    Return JSON with:
    {
      "sections": [
        {
          "title": "NEW PRODUCTS & CAPABILITIES",
          "paragraphs": [
            {
              "sentences": [
                {"text": "...", "sources":[1,3]},
                ...
              ]
            },
            ...
          ]
        }, ...
      ],
      "footnotes": [{"id":1,"title":"...","url":"https://..."}, ...]
    }
    """
    client = OpenAI(api_key=api_key)

    system_msg = (
        "You are a senior strategic AI analyst preparing a weekly 4–5 minute executive audio brief. "
        "Audience: executives and AI adoption leads. Tone: concise, on-air friendly. "
        "Return ONLY JSON following the schema I provide. "
        "Every sentence that draws from a source MUST include one or more integer IDs in `sources`. "
        "Provide at least 5 DISTINCT footnotes overall. "
        "Do not include URLs in sentence text. No inline [1] style; use the `sources` array."
    )

    categories = [
        "NEW PRODUCTS & CAPABILITIES",
        "STRATEGIC BUSINESS IMPACT",
        "IMPLEMENTATION OPPORTUNITIES",
        "MARKET DYNAMICS",
        "TALENT MARKET SHIFTS"
    ]

    headlines = fetch_headlines()

    user_msg = f"""
Write ~{int(TARGET_MIN*160)} words total (~{TARGET_MIN:0.1f}–{TARGET_MIN+0.7:0.1f} minutes).
Start with: "Hello, here is your weekly update for {intro_date_str()}."

STRUCTURE (MUST FOLLOW):
- sections: one object per category, in this exact order:
  {categories}
- Each section contains 1–2 paragraphs.
- Each paragraph is a list of sentences.
- Each sentence has:
  - text: the sentence to speak (no URLs)
  - sources: array of integer IDs (match footnotes.id) or [] if editorial commentary

FOOTNOTES REQUIREMENTS:
- footnotes: array of objects: {{id,title,url}}
- at least 5 distinct items
- ids are 1..N and referenced by sentences.sources

Optional recent headlines to consider:
{headlines}

Content guidelines:
- Be specific and useful for operators.
- You may name tools, companies, products, or people where useful.
- Avoid hype. Don't read URLs.
- Distribute sources across the sections, so most paragraphs contain at least one cited sentence.

Now return ONLY valid JSON for: sections + footnotes.
""".strip()

    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[{"role":"system","content":system_msg},{"role":"user","content":user_msg}],
        temperature=0.4,
        max_tokens=2000,
    )
    content = resp.choices[0].message.content.strip()
    try:
        data = json.loads(content)
        # Very light validation
        assert "sections" in data and "footnotes" in data
        return data
    except Exception as e:
        fail(f"Model did not return valid structured JSON: {e}\n{content}")

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

def flatten_for_voice(sections):
    """Join all sentences into an on-air script (no citations)."""
    parts = [f"Hello, here is your weekly update for {intro_date_str()}"]
    for sec in sections:
        for para in sec.get("paragraphs", []):
            sent_texts = [s.get("text","").strip() for s in para.get("sentences", []) if s.get("text")]
            if sent_texts:
                parts.append(" ".join(sent_texts))
    return "\n\n".join(parts).strip()

def main():
    api_key = os.environ.get("OPENAI_API_KEY","").strip()
    if not api_key: fail("Missing OPENAI_API_KEY")

    el_key = os.environ.get("ELEVENLABS_API_KEY","").strip()
    if not el_key: fail("Missing ELEVENLABS_API_KEY")

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID","").strip() or VOICE_ID_MAP.get(VOICE_NAME,"").strip()
    if not voice_id: fail("Missing ELEVENLABS_VOICE_ID")

    spec = (
        "Create a weekly AI executive briefing. Keep signal high, avoid filler. "
        "Distribute citations across the analysis; most paragraphs should include at least one sourced sentence."
    )

    data = openai_structured_brief(api_key, spec)
    sections = data.get("sections", [])
    footnotes = data.get("footnotes", [])

    # Persist machine-readable JSON for composing the doc/email
    Path(AUDIO_DIR).mkdir(exist_ok=True)
    base = f"ai_news_{monday_stamp()}"
    json_path = Path(AUDIO_DIR) / f"{base}.json"
    json_path.write_text(json.dumps({"sections":sections,"footnotes":footnotes}, ensure_ascii=False, indent=2), encoding="utf-8")

    # Build audio from flattened script (no citations)
    mp3_path = Path(AUDIO_DIR) / f"{base}.mp3"
    spoken = flatten_for_voice(sections)
    elevenlabs_tts(el_key, voice_id, spoken, mp3_path)

    print(f"Wrote {mp3_path} and {json_path}")

if __name__ == "__main__":
    main()
