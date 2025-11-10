#!/usr/bin/env python3
import os, sys, json, datetime as dt, requests, feedparser, re
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
    
    headlines_text = "\n".join([f"[{i+1}] {h['title']} - {h['url']}" for i, h in enumerate(headlines)])
    
    prompt = f"""Write a 4-5 minute executive AI briefing as a SPOKEN NARRATIVE.

Start with: "Hello, here is your weekly update for {intro_date_str()}. Let's dive into the latest in AI developments across five key areas."

Structure as 5 flowing paragraphs:
1. New Products & Capabilities
2. Strategic Business Impact  
3. Implementation Opportunities
4. Market Dynamics
5. Talent Market Shifts

End with: "Thank you for tuning in, and I look forward to bringing you more insights next week."

CRITICAL: Mark citations as [1], [2], etc. after sentences that reference sources. Example:
"Company X released a new model.[1] This improves efficiency by 40%.[1,3]"

Use these sources (reference by number):
{headlines_text}

Return JSON: 
{{
  "transcript_with_citations": "Full text with [1] style markers",
  "transcript_for_audio": "Same text WITHOUT any [1] markers - clean for TTS",
  "sources_used": [{{"id": 1, "title": "...", "url": "https://..."}}]
}}
"""

    resp = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2200,
    )
    
    data = json.loads(resp.choices[0].message.content)
    return data.get("transcript_with_citations", ""), data.get("transcript_for_audio", ""), data.get("sources_used", [])

def elevenlabs_tts(api_key, voice_id, text, out_mp3):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = {
        "model_id": MODEL_TTS,
        "text": text,
        "voice_settings": {
            "stability": STABILITY,
            "similarity_boost": SIMILARITY,
            "style": STYLE,
            "use_speaker_boost": SPEAKER_BOOST
        }
    }
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "content-type": "application/json"
    }
    
    print(f"Calling ElevenLabs API (text length: {len(text)} chars)...")
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    
    if r.status_code != 200:
        print(f"ERROR: ElevenLabs returned {r.status_code}", file=sys.stderr)
        print(f"Response: {r.text[:500]}", file=sys.stderr)
        sys.exit(1)
    
    out_mp3.write_bytes(r.content)
    size_mb = len(r.content) / (1024*1024)
    print(f"✓ Audio saved: {out_mp3.name} ({size_mb:.2f} MB)")

def main():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    el_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    
    if not all([api_key, el_key, voice_id]):
        print("ERROR: Missing API keys (OPENAI_API_KEY, ELEVENLABS_API_KEY, or ELEVENLABS_VOICE_ID)", file=sys.stderr)
        sys.exit(1)
    
    print("Fetching headlines...")
    headlines = fetch_headlines()
    print(f"✓ Found {len(headlines)} headlines")
    
    print("Generating brief with OpenAI...")
    transcript_cited, transcript_audio, sources = openai_narrative_brief(api_key, headlines)
    
    if not transcript_audio:
        print("ERROR: Empty transcript from OpenAI", file=sys.stderr)
        sys.exit(1)
    
    print(f"✓ Generated transcript ({len(transcript_audio)} chars, {len(sources)} sources)")
    
    AUDIO_DIR.mkdir(exist_ok=True)
    base = f"ai_news_{denver_date_today().strftime('%Y%m%d')}"
    mp3_path = AUDIO_DIR / f"{base}.mp3"
    json_path = AUDIO_DIR / f"{base}.json"
    txt_path = AUDIO_DIR / f"{base}.txt"
    
    # Generate audio (use clean version without citation markers)
    elevenlabs_tts(el_key, voice_id, transcript_audio, mp3_path)
    
    # Verify MP3 was created
    if not mp3_path.exists():
        print(f"ERROR: MP3 file not created at {mp3_path}", file=sys.stderr)
        sys.exit(1)
    
    # Save JSON with cited version for transcript display
    json_path.write_text(json.dumps({
        "spoken": transcript_cited,
        "footnotes": sources
    }, indent=2), encoding="utf-8")
    
    # Save text transcript
    lines = [transcript_cited, "", "---", "", "Sources:"]
    for src in sources:
        sid = src.get("id", "?")
        title = src.get("title", "").strip()
        url = src.get("url", "").strip()
        if url:
            lines.append(f"\n[{sid}] {title} --- {url}" if title else f"\n[{sid}] {url}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"✓ All files created successfully")
    print(f"  - {mp3_path.name}")
    print(f"  - {json_path.name}")
    print(f"  - {txt_path.name}")

if __name__ == "__main__":
    main()
