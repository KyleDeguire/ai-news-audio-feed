# scripts/update_feed.py
# Update feed.xml's enclosure to the latest MP3 and refresh dates.

from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

REPO_BASE_URL = "https://kyledeguire.github.io/ai-news-audio-feed"
AUDIO_DIR = Path("audio")
FEED_PATH = Path("feed.xml")

def rfc2822(dt: datetime) -> str:
    # RFC 2822 format in GMT (UTC)
    # Example: Tue, 16 Sep 2025 00:24:56 GMT
    return dt.astimezone(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")

def main() -> int:
    mp3_basename = os.environ.get("MP3_BASENAME", "").strip()
    stamp = os.environ.get("STAMP", "").strip()

    if not mp3_basename or not stamp:
        print("MP3_BASENAME and STAMP must be set in env.", file=sys.stderr)
        return 1

    mp3_path = AUDIO_DIR / mp3_basename
    if not mp3_path.exists():
        print(f"MP3 not found at {mp3_path}", file=sys.stderr)
        return 1

    # Calculate file size for <enclosure length="...">
    length_bytes = mp3_path.stat().st_size

    # Parse the feed (do NOT register any reserved prefixes)
    tree = ET.parse(FEED_PATH)
    root = tree.getroot()

    # Helper: find first child by tag under <channel>
    channel = root.find("channel")
    if channel is None:
        print("No <channel> in feed.xml", file=sys.stderr)
        return 1

    # Update/ensure there is at least one <item>
    item = channel.find("item")
    if item is None:
        item = ET.SubElement(channel, "item")

    # --- enclosure ---------------------------------------------------------
    enclosure = item.find("enclosure")
    if enclosure is None:
        enclosure = ET.SubElement(item, "enclosure")

    enclosure.set("url", f"{REPO_BASE_URL}/audio/{mp3_basename}")
    enclosure.set("length", str(length_bytes))
    enclosure.set("type", "audio/mpeg")

    # --- pubDate from STAMP (YYYYMMDD) ------------------------------------
    try:
        dt_pub = datetime.strptime(stamp, "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"Invalid STAMP (expected YYYYMMDD): {stamp}", file=sys.stderr)
        return 1

    pub = item.find("pubDate")
    if pub is None:
        pub = ET.SubElement(item, "pubDate")
    pub.text = rfc2822(dt_pub)

    # Ensure there is a stable <guid> (derived from stamp)
    guid = item.find("guid")
    if guid is None:
        guid = ET.SubElement(item, "guid")
    guid.text = f"ai_news_{stamp}"

    # Optional: episodeType (keep stable)
    ep_type = item.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}episodeType")
    if ep_type is None:
        # If an itunes:episodeType element already exists with another prefix, leave it.
        # Otherwise add a plain episodeType without explicit prefix (ElementTree may map it).
        ep_type = item.find("episodeType")
        if ep_type is None:
            ep_type = ET.SubElement(item, "episodeType")
    if not ep_type.text:
        ep_type.text = "full"

    # --- channel.lastBuildDate --------------------------------------------
    last_build = channel.find("lastBuildDate")
    if last_build is None:
        last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = rfc2822(datetime.now(timezone.utc))

    # Write file back. Avoid changing prefixes unnecessarily.
    # ElementTree may still emit ns0 for unknown namespaces already present in feed.xml; that’s fine.
    tree.write(FEED_PATH, encoding="utf-8", xml_declaration=True)
    print(f"feed.xml updated → enclosure={enclosure.get('url')}, length={length_bytes}, pubDate={pub.text}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
