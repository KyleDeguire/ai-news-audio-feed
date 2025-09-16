#!/usr/bin/env python3
import os, re, glob
import email.utils as eut
import datetime as dt
import xml.etree.ElementTree as ET

FEED_PATH = "feed.xml"
AUDIO_DIR = "audio"

def latest_mp3():
    files = glob.glob(os.path.join(AUDIO_DIR, "*.mp3"))
    if not files:
        raise FileNotFoundError("No MP3 files found in audio/")
    # prefer stamp in filename, else mtime
    def sort_key(p):
        m = re.search(r"(\d{8})", os.path.basename(p))
        return m.group(1) if m else dt.datetime.utcfromtimestamp(os.path.getmtime(p)).strftime("%Y%m%d")
    return sorted(files, key=sort_key, reverse=True)[0]

def stamp_from_name(name):
    m = re.search(r"(\d{8})", name)
    return m.group(1) if m else None

def rfc2822_from_stamp(stamp: str) -> str:
    d = dt.datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=dt.timezone.utc, hour=12, minute=0, second=0)
    return eut.format_datetime(d)

def human_date_from_stamp(stamp: str) -> str:
    d = dt.datetime.strptime(stamp, "%Y%m%d")
    return d.strftime("%d %b, %Y")  # e.g., 15 Sep, 2025

def text(elem, default=""):
    return elem.text if elem is not None and elem.text else default

def main():
    mp3_path = latest_mp3()
    mp3_file = os.path.basename(mp3_path)
    mp3_url  = f"https://kyledeguire.github.io/ai-news-audio-feed/{AUDIO_DIR}/{mp3_file}"
    mp3_len  = os.path.getsize(mp3_path)

    stamp = stamp_from_name(mp3_file)
    pubdate = rfc2822_from_stamp(stamp) if stamp else eut.format_datetime(dt.datetime.now(dt.timezone.utc))
    pretty  = human_date_from_stamp(stamp) if stamp else ""

    # Parse existing feed (do NOT register any reserved prefixes)
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("<channel> not found in feed.xml")

    # Use the first <item>; create if missing
    item = channel.find("item")
    if item is None:
        item = ET.SubElement(channel, "item")

    # ---- update enclosure ----
    enclosure = item.find("enclosure")
    if enclosure is None:
        enclosure = ET.SubElement(item, "enclosure")
    enclosure.set("url", mp3_url)
    enclosure.set("type", "audio/mpeg")
    enclosure.set("length", str(mp3_len))

    # ---- update pubDate ----
    pub = item.find("pubDate")
    if pub is None:
        pub = ET.SubElement(item, "pubDate")
    pub.text = pubdate

    # ---- update GUID (critical for podcast refresh) ----
    guid = item.find("guid")
    if guid is None:
        guid = ET.SubElement(item, "guid")
    guid.set("isPermaLink", "false")
    guid.text = os.path.splitext(mp3_file)[0]  # e.g., ai_news_20250915

    # ---- update Title to reflect the new date ----
    title = item.find("title")
    if title is None:
        title = ET.SubElement(item, "title")
    if pretty:
        title.text = f"AI Executive Brief - {pretty}"
    else:
        # fallback if no stamp
        title.text = "AI Executive Brief - New Episode"

    # (Optional) keep description if you want; we leave it as-is

    # ---- channel lastBuildDate ----
    lbd = channel.find("lastBuildDate")
    if lbd is None:
        lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = eut.format_datetime(dt.datetime.now(dt.timezone.utc))

    # Write updated XML
    tree.write(FEED_PATH, encoding="utf-8", xml_declaration=True)

    print(f"feed.xml updated -> {mp3_url}")
    print(f"title={title.text}  guid={guid.text}  pubDate={pub.text}")

if __name__ == "__main__":
    main()
