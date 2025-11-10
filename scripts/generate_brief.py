#!/usr/bin/env python3
import os, sys, json, datetime as dt, requests, feedparser
from pathlib import Path
from openai import OpenAI

AUDIO_DIR = Path("audio")
MODEL_TEXT = "gpt-4o-mini"
MODEL_TTS = "eleven_multilingual_v2"
STABILITY, SIMILARITY, STYLE, SPEAKER_BOOST = 0.3, 0.8, 0.1, True

SOURCES = [
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.feedburner.com/TechCrunch/artificial-intelligence",
    "https://www.marktechpost.com/feed/",
    "https://techcrunch.com/feed/",
    "https://hbr.org/topic/artificial-intelligence/feed",
]

def denver_date_today():
    import pytz
    return dt.datetime.now(pytz.timezone("America/Denver")).date()

def intro_date_str():
    d = denver_date_today()
    return f"{d.strftime('%A')}, {d.strftime('%B')} {d.day}, {d.strftime('%Y')}"

def fetch_headlines(limit=15):
    items = []
    for url in SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                title = getattr(e, "title", "").strip()
                link = getattr(e, "link", "").strip()
                if title and link:
                    items.append({"title": title, "url": link})
        except: pass
        if len(items) >= limit: break
    return items[:limit]

def openai_narrative_brief(api_key, headlines):
    client = OpenAI(api_key=api_key)
    
    headlines_text = "\n".join([f"- {h['title']} ({h['url']})" for h in headlines])
    
    prompt = f"""Write a 4-5 minute executive AI briefing as a SPOKEN NARRATIVE (not bullet points).

Start with: "Hello, here is your weekly update for {intro_date_str()}. Let's dive into the latest in AI developments across five key areas."

Structure as 5 flowing paragraphs (one per section):
1. New Products & Capabilities
2. Strategic Business Impact  
3. Implementation Opportunities
4. Market Dynamics
5. Talent Market Shifts

End with: "Thank you for tuning in, and I look forward to bringing you more insights next week."

Write in complete sentences as if speaking to executives. Be conversational, specific, professional.

Use these recent headlines for context (reference naturally, don't list them):
{headlines_text}

Return JSON: {{"spoken_transcript": "...", "sources_used": [{{"id": 1, "title": "...", "url": "https://..."}}]}}
"""

    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2000,
    )
    
    data = json.loads(resp.choices[0].message.content)
    return data.get("spoken_transcript", ""), data.get("sources_used", [])

def elevenlabs_tts(api_key, voice_id, text, out_mp3):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    r = requests.post(url, headers={"xi-api-key": api_key, "accept": "audio/mpeg", "content-type": "application/json"},
                     json={"model_id": MODEL_TTS, "text": text, 
                           "voice_settings": {"stability": STABILITY, "similarity_boost": SIMILARITY, 
                                            "style": STYLE, "use_speaker_boost": SPEAKER_BOOST}}, timeout=120)
    if r.status_code != 200:
        print(f"ElevenLabs error {r.status_code}: {r.text[:500]}", file=sys.stderr)
        sys.exit(1)
    out_mp3.write_bytes(r.content)

def main():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    el_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    
    if not all([api_key, el_key, voice_id]):
        print("Missing required API keys", file=sys.stderr)
        sys.exit(1)
    
    headlines = fetch_headlines()
    spoken, sources = openai_narrative_brief(api_key, headlines)
    
    if not spoken:
        print("Empty transcript", file=sys.stderr)
        sys.exit(1)
    
    AUDIO_DIR.mkdir(exist_ok=True)
    base = f"ai_news_{denver_date_today().strftime('%Y%m%d')}"
    mp3_path = AUDIO_DIR / f"{base}.mp3"
    json_path = AUDIO_DIR / f"{base}.json"
    txt_path = AUDIO_DIR / f"{base}.txt"
    
    # Generate audio
    print(f"Generating audio: {len(spoken)} chars")
    elevenlabs_tts(el_key, voice_id, spoken, mp3_path)
    print(f"✓ Audio generated: {mp3_path.name}")
    
    # Save structured data
    json_path.write_text(json.dumps({"spoken": spoken, "footnotes": sources}, indent=2), encoding="utf-8")
    
    # Save text transcript
    lines = [spoken, "", "---", "", "Sources:"]
    for src in sources:
        sid = src.get("id", "?")
        title = src.get("title", "").strip()
        url = src.get("url", "").strip()
        if url:
            lines.append(f"\n[{sid}] {title} --- {url}" if title else f"\n[{sid}] {url}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"✓ Files: {mp3_path.name}, {json_path.name}, {txt_path.name}")

if __name__ == "__main__":
    main()
