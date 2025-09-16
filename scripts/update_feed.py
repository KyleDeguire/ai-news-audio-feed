#!/usr/bin/env python3
import argparse, datetime as dt, email.utils as eut, os, re, sys, xml.etree.ElementTree as ET
from pathlib import Path

NS_ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ET.register_namespace("ns0", NS_ITUNES)  # show up as ns0: in your feed

def http_date_now():
    # RFC 2822 / RFC 822 format expected by podcast clients
    return eut.format_datetime(dt.datetime.utcnow(), usegmt=True)

def find_latest_mp3(audio_dir: Path) -> Path | None:
    mp3s = sorted(audio_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    return mp3s[0] if mp3s else None

def ensure_channel(tree: ET.ElementTree):
    root = tree.getroot()
    channel = root.find("channel")
    if channel is None:
        channel = ET.SubElement(root, "channel")
    return channel

def set_text(parent: ET.Element, tag: str, text: str):
    el = parent.find(tag)
    if el is None:
        el = ET.SubElement(parent, tag)
    el.text = text
    return el

def upsert_item_for(latest_url: str, channel: ET.Element) -> ET.Element:
    # Try to match an existing item with same enclosure URL; otherwise create one
    for it in channel.findall("item"):
        enc = it.find("enclosure")
        if enc is not None and enc.get("url") == latest_url:
            return it
    return ET.SubElement(channel, "item")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-url", required=True, help="Base site URL, e.g. https://kyledeguire.github.io/ai-news-audio-feed")
    ap.add_argument("--audio-dir", default="audio")
    ap.add_argument("--feed", default="feed.xml")
    ap.add_argument("--show-title", default="AI News Weekly – Executive Briefing")
    ap.add_argument("--show-description", default="Weekly AI news analysis and strategic insights for business leaders")
    ap.add_argument("--language", default="en-us")
    ap.add_argument("--artwork", default="artwork/cover.jpg")
    args = ap.parse_args()

    repo = args.repo_url.rstrip("/")
    audio_dir = Path(args.audio_dir)
    feed_path = Path(args.feed)

    latest_mp3 = find_latest_mp3(audio_dir)
    if not latest_mp3:
        print("No MP3s found in audio/; nothing to update.", file=sys.stderr)
        sys.exit(0)

    latest_url = f"{repo}/{audio_dir.as_posix()}/{latest_mp3.name}"

    # Prepare timestamps (NOW for pubDate + lastBuildDate)
    now_rfc2822 = http_date_now()

    # Create or load feed
    if feed_path.exists():
        tree = ET.parse(feed_path)
    else:
        rss = ET.Element("rss", {"version": "2.0", "xmlns:ns0": NS_ITUNES})
        tree = ET.ElementTree(rss)

    channel = ensure_channel(tree)

    # Static channel fields (idempotent)
    set_text(channel, "title", "AI News Weekly – Executive Briefing")
    set_text(channel, "description", args.show_description)
    set_text(channel, "link", repo + "/")
    set_text(channel, "language", args.language)
    set_text(channel, "lastBuildDate", now_rfc2822)

    # artwork
    image = channel.find("image")
    if image is None:
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url")
        ET.SubElement(image, "title")
        ET.SubElement(image, "link")
    set_text(image, "url", f"{repo}/{args.artwork}")
    set_text(image, "title", args.show_title)
    set_text(image, "link", repo + "/")

    # Upsert latest item
    item = upsert_item_for(latest_url, channel)
    set_text(item, "title", f"AI Executive Brief – {dt.datetime.utcnow():%d %b, %Y}")
    set_text(item, "description", "Executive Briefing: AI Market Trends and Strategic Insights")
    set_text(item, "link", repo + "/")
    set_text(item, "guid", latest_mp3.stem)  # e.g., ai_news_20250915
    set_text(item, "pubDate", now_rfc2822)   # <-- KEY: always NOW
    # enclosure
    enc = item.find("enclosure")
    if enc is None:
        enc = ET.SubElement(item, "enclosure")
    enc.set("url", latest_url)
    enc.set("type", "audio/mpeg")

    # Try to set length (optional)
    try:
        size = latest_mp3.stat().st_size
        enc.set("length", str(size))
    except Exception:
        pass

    # Write pretty-ish XML
    ET.indent(tree, space="  ")  # Python 3.9+
    tree.write(feed_path, encoding="utf-8", xml_declaration=True)
    print(f"Updated {feed_path} with pubDate={now_rfc2822} and enclosure={latest_url}")

if __name__ == "__main__":
    main()
