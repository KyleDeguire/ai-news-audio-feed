#!/usr/bin/env python3
import os, sys, time, datetime, re
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_URL = os.environ.get("PAGE_BASE_URL", "https://kyledeguire.github.io/ai-news-audio-feed")
FEED_PATH = Path("feed.xml")
AUDIO_DIR = Path("audio")

def rfc2822_now_gmt():
    return datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

def denver_date_today():
    import pytz
    return datetime.datetime.now(pytz.timezone('America/Denver')).date()

def load_stamp():
    today = denver_date_today().strftime("%Y%m%d")
    today_mp3 = AUDIO_DIR / f"ai_news_{today}.mp3"
    if today_mp3.exists():
        print(f"Found today's MP3: {today_mp3.name}")
        return today
    
    mp3s = sorted(AUDIO_DIR.glob("ai_news_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if mp3s:
        m = re.search(r"(\d{8})$", mp3s[0].stem)
        if m:
            print(f"Found newest MP3: {mp3s[0].name}")
            return m.group(1)
    
    print("No MP3 files found", file=sys.stderr)
    return None

def nice_title_from_stamp(stamp):
    try:
        return datetime.datetime.strptime(stamp, "%Y%m%d").strftime("AI Executive Brief - %d %b, %Y")
    except:
        return f"AI Executive Brief - {stamp}"

def pretty_pubdate_from_stamp(stamp):
    try:
        # FIX: Was "%Ym%d", now "%Y%m%d"
        return datetime.datetime.strptime(stamp, "%Y%m%d").strftime("%a, %d %b %Y 08:00:00 GMT")
    except:
        return rfc2822_now_gmt()

def find_latest_mp3_by_stamp(stamp):
    if stamp:
        mp3_path = AUDIO_DIR / f"ai_news_{stamp}.mp3"
        if mp3_path.exists():
            return mp3_path
    
    mp3s = sorted(AUDIO_DIR.glob("ai_news_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mp3s[0] if mp3s else None

def ensure_feed_exists():
    if not FEED_PATH.exists():
        rss = ET.Element("rss", {"version": "2.0", "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"})
        channel = ET.SubElement(rss, "channel")
        ET.SubElement(channel, "title").text = "AI News Weekly -- Executive Briefing"
        ET.SubElement(channel, "description").text = "Weekly AI news analysis and strategic insights for business leaders"
        ET.SubElement(channel, "link").text = f"{BASE_URL}/"
        ET.SubElement(channel, "language").text = "en-us"
        ET.ElementTree(rss).write(FEED_PATH, xml_declaration=True, encoding="utf-8")

def main():
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ensure_feed_exists()
    
    stamp = load_stamp()
    if not stamp:
        sys.exit(1)
    
    mp3_path = find_latest_mp3_by_stamp(stamp)
    if not mp3_path or not mp3_path.exists():
        print(f"ERROR: No MP3 found for {stamp}", file=sys.stderr)
        sys.exit(1)
    
    file_size = mp3_path.stat().st_size
    if file_size == 0:
        print(f"ERROR: MP3 is empty", file=sys.stderr)
        sys.exit(1)
    
    print(f"Processing: {mp3_path.name} ({file_size} bytes)")
    
    mp3_url = f"{BASE_URL}/audio/{mp3_path.name}?t={int(time.time())}"
    guid_text = mp3_path.stem
    
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    
    if channel is None:
        print("ERROR: Missing <channel>", file=sys.stderr)
        sys.exit(1)
    
    # Check if episode already exists
    for existing_item in channel.findall("item"):
        existing_guid = existing_item.find("guid")
        if existing_guid is not None and existing_guid.text == guid_text:
            print(f"Episode {guid_text} already exists in feed, skipping")
            sys.exit(0)
    
    print(f"Adding new episode: {guid_text}")
    
    # Build new item
    item = ET.Element("item")
    ET.SubElement(item, "title").text = nice_title_from_stamp(stamp)
    ET.SubElement(item, "description").text = "Executive Briefing: AI Market Trends and Strategic Insights"
    ET.SubElement(item, "link").text = f"{BASE_URL}/"
    
    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", mp3_url)
    enclosure.set("length", str(file_size))
    enclosure.set("type", "audio/mpeg")
    
    ET.SubElement(item, "pubDate").text = pretty_pubdate_from_stamp(stamp)
    
    guid = ET.SubElement(item, "guid")
    guid.text = guid_text
    guid.set("isPermaLink", "false")
    
    ET.SubElement(item, "itunes:explicit").text = "false"
    ET.SubElement(item, "itunes:episodeType").text = "full"
    
    # Insert at top
    first_item = channel.find("item")
    if first_item is not None:
        channel.insert(list(channel).index(first_item), item)
    else:
        channel.append(item)
    
    # Update lastBuildDate
    last_build = channel.find("lastBuildDate")
    if last_build is None:
        last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = rfc2822_now_gmt()
    
    ET.indent(tree, space="  ")
    tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")
    
    print(f"✓ Added episode: {mp3_path.name} ({file_size} bytes)")
    print(f"✓ Feed updated: {FEED_PATH}")

if __name__ == "__main__":
    main()
