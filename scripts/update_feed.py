#!/usr/bin/env python3
import sys, re, time
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

FEED = Path("feed.xml")
AUDIO_DIR = Path("audio")

# ---- helpers ----
def rfc2822_now(dt=None):
    if dt is None:
        dt = datetime.now(timezone.utc)
    # Example: Mon, 15 Sep 2025 12:00:00 GMT
    return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")

def stamp_from_filename(name: str):
    m = re.search(r"ai_news_(\d{8})\.mp3$", name)
    return m.group(1) if m else None  # e.g. '20250915'

def newest_mp3():
    mp3s = sorted(AUDIO_DIR.glob("ai_news_*.mp3"))
    if not mp3s:
        return None
    return mp3s[-1]  # filenames are date-stamped; last sorts newest

# ---- find newest audio ----
mp3 = newest_mp3()
if not mp3:
    print("No MP3 found in audio/. Nothing to do.")
    sys.exit(0)

stamp = stamp_from_filename(mp3.name)
if not stamp:
    print(f"MP3 name does not match ai_news_YYYYMMDD.mp3: {mp3.name}")
    sys.exit(1)

guid_new = f"ai_news_{stamp}"
enclosure_url = f"https://kyledeguire.github.io/ai-news-audio-feed/audio/{mp3.name}"

# ---- parse feed ----
if not FEED.exists():
    print("feed.xml is missing.")
    sys.exit(1)

tree = ET.parse(FEED)
root = tree.getroot()

# Resolve namespaces already present in your feed (itunes etc.)
nsmap = {}
for k, v in root.attrib.items():
    # not needed; just keeping future-proof parsing simple
    pass

# Find <channel>
channel = root.find("channel")
if channel is None:
    print("feed.xml has no <channel> element.")
    sys.exit(1)

# Gather existing GUIDs to avoid duplicates
existing_guids = {g.text for g in channel.findall("item/guid") if g is not None and g.text}

if guid_new in existing_guids:
    # Already published this exact episode; make sure lastBuildDate is fresh anyway
    lbd = channel.find("lastBuildDate")
    if lbd is None:
        lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = rfc2822_now()
    tree.write(FEED, encoding="utf-8", xml_declaration=True)
    print(f"GUID {guid_new} already exists; refreshed lastBuildDate.")
    sys.exit(0)

# ---- build a new <item> (prepend) ----
item = ET.Element("item")

title = ET.SubElement(item, "title")
title.text = f"AI Executive Brief - {datetime.strptime(stamp, '%Y%m%d').strftime('%d %b, %Y')}"

description = ET.SubElement(item, "description")
# keep your short synopsis; you can expand if you want
description.text = "Executive Briefing: AI Market Trends and Strategic Insights"

pubDate = ET.SubElement(item, "pubDate")
pubDate.text = rfc2822_now()

guid = ET.SubElement(item, "guid", attrib={"isPermaLink": "false"})
guid.text = guid_new

enclosure = ET.SubElement(item, "enclosure", attrib={
    "url": enclosure_url,
    "type": "audio/mpeg"
})
# (Length is optional; most apps don’t require it. Add if you really want:
# enclosure.set("length", str(mp3.stat().st_size)))

# Insert the new item right after channel metadata (before older items)
# Find index of the first existing <item>
first_item_idx = None
for idx, child in enumerate(list(channel)):
    if child.tag == "item":
        first_item_idx = idx
        break

if first_item_idx is None:
    channel.append(item)
else:
    channel.insert(first_item_idx, item)

# Update <lastBuildDate>
lbd = channel.find("lastBuildDate")
if lbd is None:
    lbd = ET.SubElement(channel, "lastBuildDate")
lbd.text = rfc2822_now()

# Write back
tree.write(FEED, encoding="utf-8", xml_declaration=True)
print(f"Published new item: {guid_new} -> {enclosure_url}")
