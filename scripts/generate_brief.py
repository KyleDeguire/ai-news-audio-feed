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
    """Generate brief in TWO separate calls to avoid JSON parsing issues"""
    client = OpenAI(api_key=api_key)
    
    headlines_text = "\n".join([f"[{i+1}] {h['title']} - {h['url']}" for i, h in enumerate(headlines)])
    
    # CALL 1: Generate the narrative (no JSON formatting issues)
    narrative_prompt = f"""Write a 4-5 minute executive AI briefing as a flowing SPOKEN NARRATIVE.

Start: "Hello, here is your weekly update for {intro_date_str()}. Let's dive into the latest in AI developments across five key areas."

5 sections (2-3 sentences each):
1. First, in new products and capabilities...
2. Moving on to strategic business impact...
3. Next, let's explore implementation opportunities...
4. Now, onto market dynamics...
5. Finally, let's discuss talent market shifts...

End: "Thank you for tuning in, and I look forward to bringing you more insights next week."

After sentences referencing these sources, add citation markers [1], [2], etc:
{headlines_text}

Write as one continuous narrative. Be conversational and executive-focused."""

    resp1 = client.chat.completions.create(
        model=MODEL_TEXT,
        messages=[{"role": "user", "content": narrative_prompt}],
        temperature=0.5,
        max_tokens=1800,
    )
    
    transcript_cited = resp1.choices[0].message.content.strip()
    
    # CALL 2: Extract which sources were actually used
    sources_prompt = f"""From this transcript, list which source numbers [1], [2], etc. were referenced:

{transcript_cited}

Available sources:
{headlines_text}

Return ONLY a JSON array of the sources that were cited: {{"sources": [{{"id": 1, "title": "...", "url": "..."}}, ...]}}"""

    resp2 = client.chat.completions.create(
        model=MODEL_TEXT,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": sources_prompt}],
        temperature=0,
        max_tokens=800,
    )
    
    try:
        sources_data = json.loads(resp2.choices[0].message.content)
        sources = sources_data.get("sources", [])
    except:
        # Fallback: return all headlines as sources
        sources = [{"id": i+1, "title": h["title"], "url": h["url"]} for i, h in enumerate(headlines)]
    
    # Create clean audio version (remove citation markers)
    transcript_audio = re.sub(r'\[\d+(?:,\d+)*\]', '', transcript_cited)
    
    return transcript_cited, transcript_audio, sources

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
    
    print(f"Calling ElevenLabs (text: {len(text)} chars)...")
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    
    if r.status_code != 200:
        print(f"ERROR: ElevenLabs {r.status_code}: {r.text[:500]}", file=sys.stderr)
        sys.exit(1)
    
    out_mp3.write_bytes(r.content)
    print(f"✓ Audio: {out_mp3.name} ({len(r.content)/(1024*1024):.2f} MB)")

def main():
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    el_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    
    if not all([api_key, el_key, voice_id]):
        print("ERROR: Missing API keys", file=sys.stderr)
        sys.exit(1)
    
    print("Fetching headlines...")
    headlines = fetch_headlines()
    print(f"✓ {len(headlines)} headlines")
    
    print("Generating brief...")
    transcript_cited, transcript_audio, sources = openai_narrative_brief(api_key, headlines)
    
    if not transcript_audio:
        print("ERROR: Empty transcript", file=sys.stderr)
        sys.exit(1)
    
    print(f"✓ Transcript: {len(transcript_audio)} chars, {len(sources)} sources")
    
    AUDIO_DIR.mkdir(exist_ok=True)
    base = f"ai_news_{denver_date_today().strftime('%Y%m%d')}"
    mp3_path = AUDIO_DIR / f"{base}.mp3"
    json_path = AUDIO_DIR / f"{base}.json"
    txt_path = AUDIO_DIR / f"{base}.txt"
    
    # Audio generation
    elevenlabs_tts(el_key, voice_id, transcript_audio, mp3_path)
    
    if not mp3_path.exists():
        print(f"ERROR: MP3 not created", file=sys.stderr)
        sys.exit(1)
    
    # Save files
    json_path.write_text(json.dumps({"spoken": transcript_cited, "footnotes": sources}, indent=2), encoding="utf-8")
    
    lines = [transcript_cited, "", "---", "", "Sources:"]
    for s in sources:
        sid, title, url = s.get("id", "?"), (s.get("title") or "").strip(), (s.get("url") or "").strip()
        if url:
            lines.append(f"\n[{sid}] {title} --- {url}" if title else f"\n[{sid}] {url}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    
    print(f"✓ Complete: {mp3_path.name}, {json_path.name}, {txt_path.name}")

if __name__ == "__main__":
    main()
