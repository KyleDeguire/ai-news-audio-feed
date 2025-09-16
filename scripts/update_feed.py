#!/usr/bin/env python3
import os
import re
import glob
import email.utils as eut
import datetime as dt
import xml.etree.ElementTree as ET

FEED_PATH = "feed.xml"
AUDIO_DIR = "audio"

def latest_mp3():
    files = sorted(glob.glob(os.path.join(AUDIO_DIR, "*.mp3")))
    if not files:
        raise FileNotFoundError("No MP3 files found in audio/")
    # Sort by stamp in filename if present, else by mtime
    def key_fn(p):
        m = re.search(r'(\d{8})', os.path.basename(p))
        if m:
            return m.group(1)
        return dt.datetime.utcfromtimestamp(os.path.getmtime(p)).strftime("%Y%m%d")
    files.sort(key=key_fn, reverse=True)
    return files[0]

def rfc2822_from_stamp(stamp: str) -> str:
    """stamp like 20250914 -> Sun, 14 Sep 2025 12:00:00 GMT"""
    d = dt.datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=dt.timezone.utc)
    # Noon UTC gives stable cross-platform sort; adjust if you prefer a fixed hour
    d = d.replace(hour=12, minute=0, second=0)
    return eut.format_datetime(d)

def main():
    mp3_path = latest_mp3()
    mp3_file = os.path.basename(mp3_path)
    mp3_url = f"https://kyledeguire.github.io/ai-news-audio-feed/{AUDIO_DIR}/{mp3_file}"
    mp3_len = os.path.getsize(mp3_path)

    # Try to derive a pubDate from filename stamp, else from file mtime
    m = re.search(r'(\d{8})', mp3_file)
    if m:
        pubdate = rfc2822_from_stamp(m.group(1))
    else:
        pubdate = eut.format_datetime(
            dt.datetime.utcfromtimestamp(os.path.getmtime(mp3_path)).replace(tzinfo=dt.timezone.utc)
        )

    # Parse XML WITHOUT registering any reserved prefixes
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()

    # Build a namespace map from the existing XML (don’t register/rename anything)
    ns = {}
    for k, v in root.attrib.items():
        if k.startswith("{http://www.w3.org/2000/xmlns/}"):
            ns[k.split("}", 1)[1]] = v
    # Helpful defaults for searches (not strictly required for what we touch)
    itunes_prefix = next((p for p, uri in ns.items() if "itunes.com/dtds/podcast-1.0.dtd" in uri), None)

    # Get <channel> and its first <item>
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("feed.xml: <channel> not found")

    item = channel.find("item")
    if item is None:
        # If no item exists, create one minimally (apps still parse it fine)
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = "New Episode"
        ET.SubElement(item, "description").text = "Auto-generated episode."
        ET.SubElement(item, "guid").text = os.path.splitext(mp3_file)[0]
        ET.SubElement(item, "enclosure")

    # Update enclosure
    enclosure = item.find("enclosure")
    if enclosure is None:
        enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", mp3_url)
    enclosure.set("type", "audio/mpeg")
    # Optional: set length (some podcast directories like it)
    enclosure.set("length", str(mp3_len))

    # Update pubDate on the item
    pub = item.find("pubDate")
    if pub is None:
        pub = ET.SubElement(item, "pubDate")
    pub.text = pubdate

    # Update channel lastBuildDate
    now_utc = eut.format_datetime(dt.datetime.now(dt.timezone.utc))
    lbd = channel.find("lastBuildDate")
    if lbd is None:
        lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = now_utc

    # Write back (ElementTree will preserve existing prefixes; we didn’t register anything)
    tree.write(FEED_PATH, encoding="utf-8", xml_declaration=True)

    print(f"Updated feed.xml -> {mp3_url} ({mp3_len} bytes) pubDate={pubdate}")

if __name__ == "__main__":
    main()
