#!/usr/bin/env python3
import os, re, time, argparse
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from email.utils import formatdate

def rfc822_now():
    return formatdate(timeval=None, localtime=False, usegmt=True)

def rfc822_from_date(dt):
    return formatdate(time.mktime(dt.timetuple()), usegmt=True)

def parse_date_from_filename(fn):
    m = re.search(r"(\d{8})", fn)
    if m:
        try:
            d = datetime.strptime(m.group(1), "%Y%m%d")
            d = d.replace(tzinfo=timezone.utc, hour=12)
            return d
        except:
            pass
    return datetime.now(timezone.utc)

def update_feed(feed_path, base_url, audio_dir, title, desc, lang):
    if os.path.exists(feed_path):
        tree = ET.parse(feed_path)
        root = tree.getroot()
    else:
        root = ET.Element("rss", version="2.0")
        tree = ET.ElementTree(root)

    channel = root.find("channel")
    if channel is None:
        channel = ET.SubElement(root, "channel")

    # Basic channel info
    for tag, text in [("title", title), ("description", desc),
                      ("link", base_url + "/"), ("language", lang)]:
        el = channel.find(tag)
        if el is None: el = ET.SubElement(channel, tag)
        el.text = text

    lbd = channel.find("lastBuildDate")
    if lbd is None: lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = rfc822_now()

    # Find latest mp3
    mp3s = [f for f in os.listdir(audio_dir) if f.endswith(".mp3")]
    if not mp3s:
        raise SystemExit("No MP3s found in audio/")
    latest = sorted(mp3s)[-1]
    size = os.path.getsize(os.path.join(audio_dir, latest))
    pubdate = rfc822_from_date(parse_date_from_filename(latest))
    guid_val = os.path.splitext(latest)[0]
    url = f"{base_url}/audio/{latest}"

    # Remove duplicates
    for item in channel.findall("item"):
        guid = item.find("guid")
        if guid is not None and guid.text == guid_val:
            channel.remove(item)

    # Create item
    item = ET.Element("item")
    ET.SubElement(item, "title").text = f"AI Executive Brief - {pubdate.split()[1]} {pubdate.split()[2]}, {pubdate.split()[3]}"
    ET.SubElement(item, "description").text = "Executive Briefing: AI Market Trends and Strategic Insights"
    ET.SubElement(item, "enclosure", url=url, length=str(size), type="audio/mpeg")
    ET.SubElement(item, "pubDate").text = pubdate
    ET.SubElement(item, "guid").text = guid_val

    channel.insert(0, item)

    ET.indent(tree, "  ")
    tree.write(feed_path, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-url", required=True)
    ap.add_argument("--audio-dir", default="audio")
    ap.add_argument("--feed", default="feed.xml")
    ap.add_argument("--show-title", default="AI News Weekly – Executive Briefing")
    ap.add_argument("--show-description", default="Weekly AI news analysis and strategic insights for business leaders")
    ap.add_argument("--language", default="en-us")
    args = ap.parse_args()
    update_feed(args.feed, args.repo_url, args.audio_dir,
                args.show_title, args.show_description, args.language)
