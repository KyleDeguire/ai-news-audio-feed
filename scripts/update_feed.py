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
    # Prefer explicit STAMP environment variable (format YYYYMMDD or similar)
    s = os.environ.get("STAMP")
    if s:
        return s
    # Fallback: try to infer from newest audio filename like ai_news_YYYYMMDD.mp3
    mp3s = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    if mp3s:
        name = mp3s[0].stem  # e.g. ai_news_20250916
        # grab trailing 8-digit part
        import re
        m = re.search(r"(\d{8})$", name)
        if m:
            return m.group(1)
    return None

def nice_title_from_stamp(stamp):
    # Try parse YYYYMMDD
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
    # prefer filename containing stamp
    if stamp:
        candidates = list(AUDIO_DIR.glob(f"*{stamp}*.mp3"))
        if candidates:
            # return the newest matching file
            return sorted(candidates, key=os.path.getmtime, reverse=True)[0]
    # fallback: newest mp3
    mp3s = sorted(AUDIO_DIR.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    return mp3s[0] if mp3s else None

def register_namespaces():
    # Use common prefixes to avoid ElementTree creating ns0, ns1, etc.
    # Do NOT try to register 'ns0' (reserved); register a readable prefix instead.
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

def ensure_feed_exists():
    if not FEED_PATH.exists():
        # create a minimal template feed if missing
        channel = ET.Element("channel")
        ET.SubElement(channel, "title").text = "AI News Weekly – Executive Briefing"
        ET.SubElement(channel, "link").text = f"{BASE_URL}/"
        ET.SubElement(channel, "description").text = "Weekly AI news analysis and strategic insights for business leaders"
        ET.SubElement(channel, "language").text = "en-us"
        tree = ET.ElementTree(ET.Element("rss", {"version": "2.0"}))
        tree.getroot().append(channel)
        tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")

def main():
    register_namespaces()
    ensure_feed_exists()

    stamp = load_stamp()
    if not stamp:
        print("ERROR: STAMP not found and no audio files to infer from.", file=sys.stderr)
        sys.exit(1)

    mp3_path = find_latest_mp3_by_stamp(stamp)
    if not mp3_path or not mp3_path.exists():
        print("ERROR: No MP3 found for stamp:", stamp, file=sys.stderr)
        sys.exit(1)

    mp3_basename = mp3_path.name
    mp3_url = f"{BASE_URL}/audio/{mp3_basename}"
    mp3_size = str(mp3_path.stat().st_size)

    # guid derive (unique per new episode)
    guid_text = mp3_basename.replace(".mp3", "")

    # parse feed
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()
    # find channel (rss -> channel)
    channel = root.find("channel")
    if channel is None:
        # try with namespace fallback
        for c in root:
            if c.tag.lower().endswith("channel"):
                channel = c
                break
    if channel is None:
        print("ERROR: feed.xml missing <channel>", file=sys.stderr)
        sys.exit(1)

    # check for existing guid (avoid duplicates)
    existing_guids = { (item.find("guid").text if item.find("guid") is not None else "") for item in channel.findall("item") }
    if guid_text in existing_guids:
        print(f"Episode for guid {guid_text} already in feed — skipping append.")
        # still update lastBuildDate to current time so feed consumers might see freshness
        last = channel.find("lastBuildDate")
        if last is None:
            last = ET.SubElement(channel, "lastBuildDate")
        last.text = rfc2822_now_gmt()
        tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")
        sys.exit(0)

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

    # insert the new item at the top (before any existing items) so feed is newest-first
    first_item = channel.find("item")
    if first_item is not None:
        # insert before first_item
        channel.insert(list(channel).index(first_item), item)
    else:
        channel.append(item)

    # update lastBuildDate to now
    last = channel.find("lastBuildDate")
    if last is None:
        last = ET.SubElement(channel, "lastBuildDate")
    last.text = rfc2822_now_gmt()

    # write back
    tree.write(FEED_PATH, xml_declaration=True, encoding="utf-8")
    print("Appended new item to feed:", mp3_basename)
    sys.exit(0)

if __name__ == "__main__":
    main()
