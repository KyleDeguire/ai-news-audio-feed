#!/usr/bin/env python3
# scripts/update_feed.py
# Appends a new <item> to feed.xml for the latest MP3 (idempotent: will not duplicate an existing guid)

import os
import sys
import glob
import time
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path

# CONFIG: adjust only if you host the feed at a different base URL
BASE_URL = os.environ.get("PAGE_BASE_URL", "https://kyledeguire.github.io/ai-news-audio-feed")
FEED_PATH = Path("feed.xml")
AUDIO_DIR = Path("audio")

def rfc2822_now_gmt():
    now = datetime.datetime.utcnow()
    return now.strftime("%a, %d %b %Y %H:%M:%S GMT")

def load_stamp():
    # Always process the newest MP3 file, regardless of date
    mp3s = sorted(AUDIO_DIR.glob("ai_news_*.mp3"), key=os.path.getmtime, reverse=True)
    if mp3s:
        name = mp3s[0].stem  # e.g. ai_news_20250915
        # Extract the 8-digit date from filename
        import re
        m = re.search(r"(\d{8})$", name)
        if m:
            print(f"Found newest MP3: {mp3s[0].name} with stamp: {m.group(1)}")
            return m.group(1)
    
    print("No ai_news_*.mp3 files found")
    return None

def nice_title_from_stamp(stamp):
    try:
        d = datetime.datetime.strptime(stamp, "%Y%m%d")
        return d.strftime("AI Executive Brief - %d %b, %Y")
    except Exception:
        return f"AI Executive Brief - {stamp}"

def pretty_pubdate_from_stamp(stamp):
    try:
        d = datetime.datetime.strptime(stamp, "%Y%m%d")
        return d.strftime("%a, %d %b %Y %H:%M:%S GMT")
    except Exception:
        return rfc2822_now_gmt()

def find_latest_mp3_by_stamp(stamp):
    if stamp:
        candidates = list(AUDIO_DIR.glob(f"*{stamp}*.mp3"))
        if candidates:
            return sorted(candidates, key=os.path.getmtime, reverse=True)[0]
    
    # fallback: newest ai_news mp3
    mp3s = sorted(AUDIO_DIR.glob("ai_news_*.mp3"), key=os.path.getmtime, reverse=True)
    return mp3s[0] if mp3s else None

def register_namespaces():
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

def create_proper_feed():
    """Create a properly structured RSS feed"""
    rss = ET.Element("rss", {"version": "2.0"})
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    
    channel = ET.SubElement(rss, "channel")
    
    # Channel metadata (must come first)
    ET.SubElement(channel, "title").text = "AI News Weekly -- Executive Briefing"
    ET.SubElement(channel, "description").text = "Weekly AI news analysis and strategic insights for business leaders"
    ET.SubElement(channel, "link").text = f"{BASE_URL}/"
    ET.SubElement(channel, "language").text = "en-us"
    ET.SubElement(channel, "lastBuildDate").text = rfc2822_now_gmt()
    
    # iTunes specific tags
    itunes_image = ET.SubElement(channel, "itunes:image")
    itunes_image.set("href", f"{BASE_URL}/artwork/cover.jpg")
    
    itunes_category = ET.SubElement(channel, "itunes:category")
    itunes_category.set("text", "News")
    itunes_sub_category = ET.SubElement(itunes_category, "itunes:category")
    itunes_sub_category.set("text", "Tech News")
    
    ET.SubElement(channel, "itunes:explicit").text = "false"
    
    tree = ET.ElementTree(rss)
    tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")
    return tree

def ensure_feed_exists():
    if not FEED_PATH.exists():
        create_proper_feed()

def main():
    register_namespaces()
    ensure_feed_exists()
    
    stamp = load_stamp()
    if not stamp:
        print("ERROR: No audio files found to process.", file=sys.stderr)
        sys.exit(1)
    
    mp3_path = find_latest_mp3_by_stamp(stamp)
    if not mp3_path or not mp3_path.exists():
        print(f"ERROR: No MP3 found for stamp: {stamp}", file=sys.stderr)
        sys.exit(1)
    
    mp3_basename = mp3_path.name
    mp3_url = f"{BASE_URL}/audio/{mp3_basename}"
    mp3_size = str(mp3_path.stat().st_size)
    
    # guid derive (unique per new episode)
    guid_text = mp3_basename.replace(".mp3", "")
    
    print(f"Processing: {mp3_basename} with GUID: {guid_text}")
    
    # parse feed
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()
    
    # find channel
    channel = root.find("channel")
    if channel is None:
        print("ERROR: feed.xml missing <channel>", file=sys.stderr)
        sys.exit(1)
    
    # check for existing guid (avoid duplicates)
    existing_guids = set()
    for item in channel.findall("item"):
        guid_elem = item.find("guid")
        if guid_elem is not None and guid_elem.text:
            existing_guids.add(guid_elem.text)
    
    print(f"Existing GUIDs in feed: {existing_guids}")
    
    if guid_text in existing_guids:
        print(f"Episode for GUID {guid_text} already in feed --- skipping append.")
        # still update lastBuildDate
        last = channel.find("lastBuildDate")
        if last is None:
            last = ET.SubElement(channel, "lastBuildDate")
        last.text = rfc2822_now_gmt()
        tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")
        sys.exit(0)
    
    print(f"Adding new episode with GUID: {guid_text}")
    
    # Construct new item
    item = ET.Element("item")
    
    title = ET.SubElement(item, "title")
    title.text = nice_title_from_stamp(stamp)
    
    desc = ET.SubElement(item, "description")
    desc.text = "Executive Briefing: AI Market Trends and Strategic Insights"
    
    link = ET.SubElement(item, "link")
    link.text = f"{BASE_URL}/"
    
    enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", mp3_url)
    enclosure.set("length", mp3_size)
    enclosure.set("type", "audio/mpeg")
    
    pubDate = ET.SubElement(item, "pubDate")
    pubDate.text = pretty_pubdate_from_stamp(stamp)
    
    guid = ET.SubElement(item, "guid")
    guid.text = guid_text
    guid.set("isPermaLink", "false")
    
    # iTunes episode metadata
    ET.SubElement(item, "itunes:explicit").text = "false"
    ET.SubElement(item, "itunes:episodeType").text = "full"
    
    # Insert the new item at the top (newest first)
    first_item = channel.find("item")
    if first_item is not None:
        channel.insert(list(channel).index(first_item), item)
    else:
        channel.append(item)
    
    # update lastBuildDate
    last = channel.find("lastBuildDate")
    if last is None:
        last = ET.SubElement(channel, "lastBuildDate")
    last.text = rfc2822_now_gmt()
    
    # write back with proper formatting
    ET.indent(tree, space="  ")
    tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")
    
    print(f"Successfully added new episode: {mp3_basename}")
    sys.exit(0)

if __name__ == "__main__":
    main()
