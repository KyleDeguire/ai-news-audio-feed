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
    "https://news.ycombinator.com/rss",
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

def renumber_citations(text, sources_map):
    citation_pattern = r'\[(\d+(?:,\s*\d+)*)\]'
    citations_found = []
    
    for match in re.finditer(citation_pattern, text):
        nums = [int(n.strip()) for n in match.group(1).split(',')]
        for num in nums:
            if num not in citations_found and num in sources_map:
                citations_found.append(num)
    
    renumber_map = {old_id: idx + 1 for idx, old_id in enumerate(citations_found)}
    
    def replace_citation(match):
        old_nums = [int(n.strip()) for n in match.group(1).split(',')]
        new_nums = sorted(set(renumber_map.get(n) for n in old_nums if n in renumber_map))
        if not new_nums:
            return ''
        return f"[{','.join(str(n) for n in new_nums)}]"
    
    cleaned_text = re.sub(citation_pattern, replace_citation, text)
    
    renumbered_sources = []
    for old_id in citations_found:
        if old_id in sources_map:
            src = sources_map[old_id].copy()
            src['id'] = renumber_map[old_id]
            renumbered_sources.append(src)
    
    return cleaned_text, renumbered_sources

def openai_narrative_brief(api_key, headlines):
    client = OpenAI(api_key=api_key)
    
    headlines_text = "\n".join([f"[{i+1}] {h['title']} - {h['url']}" for i, h in enumerate(headlines)])
    
    narrative_prompt = f"""Write a 4-5 minute executive AI briefing with clear section headers.

CRITICAL FORMAT RULES:
- Write section headers on their OWN line: "Introduction:"
- Put content in paragraphs BELOW each header
- Do NOT use **bold markdown** anywhere
- Use plain text only

Start with:
Introduction:
Hello, here is your weekly update for {intro_date_str()}. Let's dive into the latest in AI developments across five key areas.

Structure (each header on its own line, content below):
New Products & Capabilities:
First, in new products and capabilities...[content with citations]

Strategic Business Impact:
Moving on to strategic business impact...[content with citations]

Implementation Opportunities:
Next, let's explore implementation opportunities...[content with citations]

Market Dynamics:
Now, onto market dynamics...[content with citations]

Talent Market Shifts:
Finally, let's discuss talent market shifts...[content with citations]

End with: "Thank you for tuning in, and I look forward to bringing you more insights next week."

CITATION RULES:
- After EVERY factual claim, add [1], [2], etc.
- Cite 3-5 times per section
- ONLY use source numbers 1-15

Sources:
{headlines_text}

Write flowing narrative with frequent citations. NO MARKDOWN FORMATTING."""

    resp1 = client.chat.completions.create(
        model=MODEL_TEXT,
        messages=[{"role": "user", "content": narrative_prompt}],
        temperature=0.5,
        max_tokens=1800,
    )
    
    transcript_raw = resp1.choices[0].message.content.strip()
    
    # Remove any markdown formatting that OpenAI might add
    transcript_raw = re.sub(r'\*\*([^*]+)\*\*', r'\1', transcript_raw)
    transcript_raw = re.sub(r'\*([^*]+)\*', r'\1', transcript_raw)
    
    sources_map = {i+1: {"id": i+1, "title": h["title"], "url": h["url"]} for i, h in enumerate(headlines)}
    transcript_cited, sources_used = renumber_citations(transcript_raw, sources_map)
    transcript_audio = re.sub(r'\[\d+(?:,\d+)*\]', '', transcript_cited)
    
    # Remove section headers from audio
    audio_clean = transcript_audio
    for header in ["Introduction:", "New Products & Capabilities:", "Strategic Business Impact:", 
                   "Implementation Opportunities:", "Market Dynamics:", "Talent Market Shifts:"]:
        audio_clean = audio_clean.replace(header, "")
    
    return transcript_cited, audio_clean, sources_used

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
    
    print(f"✓ Transcript: {len(transcript_audio)} chars, {len(sources)} sources cited")
    
    AUDIO_DIR.mkdir(exist_ok=True)
    base = f"ai_news_{denver_date_today().strftime('%Y%m%d')}"
    mp3_path = AUDIO_DIR / f"{base}.mp3"
    json_path = AUDIO_DIR / f"{base}.json"
    txt_path = AUDIO_DIR / f"{base}.txt"
    
    elevenlabs_tts(el_key, voice_id, transcript_audio, mp3_path)
    
    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
        print(f"ERROR: MP3 not created or empty", file=sys.stderr)
        sys.exit(1)
    
    print(f"✓ MP3 verified: {mp3_path.stat().st_size / (1024*1024):.2f} MB")
    
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
