#!/usr/bin/env python3
"""
Deterministic feed updater:
- Finds newest audio/ai_news_YYYYMMDD.mp3 (by stamp in filename; fallback mtime)
- PREPENDS a brand-new <item> (does not mutate prior items)
- Sets unique <guid isPermaLink="false">ai_news_YYYYMMDD</guid>
- Sets <title>AI Executive Brief - DD Mon, YYYY</title>
- Sets <pubDate> to now (RFC 2822)
- Points <enclosure> to the exact mp3 URL, sets type and length
- Updates channel <lastBuildDate> to now
- Leaves existing channel metadata and older items intact
"""

from __future__ import annotations
import re, sys
from pathlib import Path
from datetime import datetime, timezone
import email.utils as eut
import xml.etree.ElementTree as ET

REPO_BASE = "https://kyledeguire.github.io/ai-news-audio-feed"
FEED_PATH = Path("feed.xml")
AUDIO_DIR = Path("audio")

STAMP_RE = re.compile(r"ai_news_(\d{8})\.mp3$", re.IGNORECASE)

def rfc2822_now() -> str:
    return eut.format_datetime(datetime.now(timezone.utc), usegmt=True)

def human_date_from_stamp(stamp: str) -> str:
    d = datetime.strptime(stamp, "%Y%m%d")
    return d.strftime("%d %b, %Y")  # e.g., 15 Sep, 2025

def pick_latest_mp3() -> Path:
    # Prefer stamped filenames; else fallback to newest by mtime
    stamped = sorted(AUDIO_DIR.glob("ai_news_*.mp3"))
    if stamped:
        # sort by numeric stamp ascending, take last
        stamped = sorted(stamped, key=lambda p: STAMP_RE.search(p.name).group(1) if STAMP_RE.search(p.name) else p.name)
        return stamped[-1]
    all_mp3 = sorted(AUDIO_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    if not all_mp3:
        sys.exit("No MP3 found under audio/")
    return all_mp3[-1]

def ensure_channel(root: ET.Element) -> ET.Element:
    ch = root.find("channel")
    if ch is None:
        ch = ET.SubElement(root, "channel")
    return ch

def main():
    if not FEED_PATH.exists():
        sys.exit("feed.xml missing")

    mp3 = pick_latest_mp3()
    mp3_name = mp3.name
    m = STAMP_RE.search(mp3_name)
    if not m:
        sys.exit(f"MP3 does not match ai_news_YYYYMMDD.mp3: {mp3_name}")
    stamp = m.group(1)
    guid_text = f"ai_news_{stamp}"
    enclosure_url = f"{REPO_BASE}/audio/{mp3_name}"
    enclosure_len = str(mp3.stat().st_size)
    now_rfc = rfc2822_now()
    title_text = f"AI Executive Brief - {human_date_from_stamp(stamp)}"

    # Parse without registering any prefixes; we won't touch itunes tags
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()
    channel = ensure_channel(root)

    # Collect existing GUIDs to avoid dup insertion
    existing_guids = {g.text for g in channel.findall("item/guid") if g is not None and g.text}
    if guid_text in existing_guids:
        # Already present. Just bump lastBuildDate and exit.
        lbd = channel.find("lastBuildDate")
        if lbd is None: lbd = ET.SubElement(channel, "lastBuildDate")
        lbd.text = now_rfc
        tree.write(FEED_PATH, encoding="utf-8", xml_declaration=True)
        print(f"[update_feed] GUID already present: {guid_text}. Refreshed lastBuildDate.")
        return

    # Build a brand-new item
    item = ET.Element("item")
    ET.SubElement(item, "title").text = title_text
    ET.SubElement(item, "description").text = "Executive Briefing: AI Market Trends and Strategic Insights"
    ET.SubElement(item, "pubDate").text = now_rfc
    g = ET.SubElement(item, "guid", attrib={"isPermaLink": "false"})
    g.text = guid_text
    enc = ET.SubElement(item, "enclosure", attrib={
        "url": enclosure_url,
        "type": "audio/mpeg",
        "length": enclosure_len
    })

    # Prepend: insert before first existing <item>, else append
    inserted = False
    for idx, child in enumerate(list(channel)):
        if child.tag == "item":
            channel.insert(idx, item)
            inserted = True
            break
    if not inserted:
        channel.append(item)

    # Update channel lastBuildDate
    lbd = channel.find("lastBuildDate")
    if lbd is None: lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = now_rfc

    tree.write(FEED_PATH, encoding="utf-8", xml_declaration=True)
    print(f"[update_feed] Prepended item: {guid_text} -> {enclosure_url}")

if __name__ == "__main__":
    main()
