#!/usr/bin/env python3
"""
Update feed.xml by PREPENDING a new <item> for the latest MP3.
Keeps older items intact so podcast apps see a brand-new GUID each week.

Inputs (from env, all plain strings):
  FEED_PATH        => path to feed.xml (e.g., "feed.xml")
  AUDIO_DIR        => relative dir where MP3 lives (e.g., "audio")
  MP3_BASENAME     => filename only (e.g., "ai_news_20250916.mp3")
  STAMP            => episode id fragment (e.g., "20250916")
  READABLE_DATE    => e.g., "Mon, Sep 16, 2025"
  EPISODE_TITLE    => short headline/title (optional; will be prefixed by date)
  SITE_LINK        => site root link already in <channel><link> (optional override)
"""

import os
import time
import email.utils as eut
import xml.etree.ElementTree as ET

def findfirst(parent, name):
    for el in parent:
        if el.tag.endswith(name):
            return el
    return None

def findall(parent, name):
    return [el for el in parent if el.tag.endswith(name)]

def text(el):
    return "" if el is None or el.text is None else el.text

def main():
    feed_path     = os.getenv("FEED_PATH", "feed.xml")
    audio_dir     = os.getenv("AUDIO_DIR", "audio")
    mp3_basename  = os.getenv("MP3_BASENAME", "").strip()
    stamp         = os.getenv("STAMP", "").strip()
    readable_date = os.getenv("READABLE_DATE", "").strip()
    headline      = os.getenv("EPISODE_TITLE", "").strip()
    site_link_ovr = os.getenv("SITE_LINK", "").strip()

    if not mp3_basename or not stamp:
        raise SystemExit("MP3_BASENAME and STAMP must be set.")

    # Load feed
    tree = ET.parse(feed_path)
    root = tree.getroot()

    # <channel>
    channel = findfirst(root, "channel")
    if channel is None:
        raise SystemExit("feed.xml has no <channel>")

    # Derive base URL from <channel><link> unless overridden
    ch_link_el = findfirst(channel, "link")
    base_url = site_link_ovr or (text(ch_link_el).rstrip("/") + "/")
    if not base_url.endswith("/"):
        base_url += "/"

    # Build absolute MP3 URL and file size
    enclosure_url = f"{base_url}{audio_dir}/{mp3_basename}"
    mp3_path = os.path.join(audio_dir, mp3_basename)
    length = "0"
    try:
        length = str(os.path.getsize(mp3_path))
    except Exception:
        # If length can’t be stat’d, leave 0 – still valid for most podcatchers
        pass

    # Publish date: RFC 2822 in GMT
    pubdate = eut.formatdate(usegmt=True)

    # Title & description
    # Example final title: "AI Executive Brief – 16 Sep, 2025"
    # If you pass EPISODE_TITLE, it’s used as the description’s lead.
    title_text = f"AI Executive Brief – {readable_date or stamp}"
    desc_lead  = headline or "Executive Briefing"
    description_text = f"{desc_lead}: AI Market Trends and Strategic Insights"

    # GUID for this episode
    guid_value = f"ai_news_{stamp}"

    # If an item with this guid already exists, drop it first (idempotent)
    for existing in reversed(findall(channel, "item")):
        g = findfirst(existing, "guid")
        if g is not None and text(g) == guid_value:
            channel.remove(existing)

    # Create new <item>
    item = ET.Element("item")

    el_title = ET.SubElement(item, "title")
    el_title.text = title_text

    el_desc = ET.SubElement(item, "description")
    el_desc.text = description_text

    el_link = ET.SubElement(item, "link")
    el_link.text = text(ch_link_el) or base_url

    el_guid = ET.SubElement(item, "guid")
    el_guid.text = guid_value

    el_pub = ET.SubElement(item, "pubDate")
    el_pub.text = pubdate

    el_encl = ET.SubElement(item, "enclosure")
    el_encl.set("url", enclosure_url)
    el_encl.set("type", "audio/mpeg")
    el_encl.set("length", length)

    # Insert as the FIRST <item> (so new episodes appear at top)
    children = list(channel)
    first_item_idx = None
    for idx, el in enumerate(children):
        if el.tag.endswith("item"):
            first_item_idx = idx
            break

    if first_item_idx is None:
        channel.append(item)
    else:
        channel.insert(first_item_idx, item)

    # Update <lastBuildDate>
    lbd = findfirst(channel, "lastBuildDate")
    if lbd is None:
        lbd = ET.SubElement(channel, "lastBuildDate")
    lbd.text = eut.formatdate(usegmt=True)

    # Write out without altering namespaces/prefixes
    tree.write(feed_path, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    main()
