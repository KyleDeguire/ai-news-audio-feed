#!/usr/bin/env python3
import argparse
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from xml.sax.saxutils import escape

DATE_SUFFIX = re.compile(r".*_(\d{8})\.mp3$", re.IGNORECASE)

def newest_mp3(audio_dir: Path) -> Path:
    mp3s = sorted(audio_dir.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp3s:
        sys.exit("update_feed.py: No MP3s found in audio/")
    return mp3s[0]

def parse_stamp_from_filename(mp3_name: str) -> datetime:
    """
    Expect filenames like ai_news_20250915.mp3 -> 2025-09-15 12:00:00Z (noon UTC for stability)
    """
    m = DATE_SUFFIX.match(mp3_name)
    if not m:
        # Fallback: now (still valid RSS)
        return datetime.now(timezone.utc)
    yyyymmdd = m.group(1)
    dt = datetime.strptime(yyyymmdd, "%Y%m%d").replace(tzinfo=timezone.utc)
    # Fix a stable publish time (noon UTC) so feeds don't flap
    return dt.replace(hour=12, minute=0, second=0, microsecond=0)

def file_length_bytes(p: Path) -> int:
    try:
        return p.stat().st_size
    except FileNotFoundError:
        return 0

def build_item_xml(title: str, link: str, guid: str, pub_date: datetime, enclosure_url: str, enclosure_len: int) -> str:
    return f"""  <item>
    <title>{escape(title)}</title>
    <description>Executive Briefing: AI Market Trends and Strategic Insights</description>
    <link>{escape(link)}</link>
    <pubDate>{formatdate(pub_date.timestamp(), usegmt=True)}</pubDate>
    <guid>{escape(guid)}</guid>
    <enclosure url="{escape(enclosure_url)}" length="{enclosure_len}" type="audio/mpeg"/>
    <ns0:explicit>false</ns0:explicit>
    <ns0:episodeType>full</ns0:episodeType>
  </item>
"""

def build_feed_xml(
    show_title: str,
    show_description: str,
    language: str,
    site_link: str,
    image_url: str | None,
    item_xml: str,
) -> str:
    last_build = formatdate(time.time(), usegmt=True)
    image_block = f'  <ns0:image href="{escape(image_url)}"/>\n' if image_url else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ns0="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
<channel>
{image_block}  <ns0:category text="News"/>
  <ns0:category text="Tech News"/>
  <ns0:explicit>false</ns0:explicit>

  <title>{escape(show_title)}</title>
  <description>{escape(show_description)}</description>
  <link>{escape(site_link)}</link>

{item_xml.strip()}

  <title>AI News Weekly — Executive Briefing</title>
  <description>Weekly AI news analysis and strategic insights for business leaders</description>
  <link>{escape(site_link)}</link>
  <language>{escape(language)}</language>
  <lastBuildDate>{last_build}</lastBuildDate>
</channel>
</rss>
"""

def main():
    ap = argparse.ArgumentParser(description="Update simple podcast RSS pointing to latest audio.")
    ap.add_argument("--repo-url", required=True, help="Base site URL, e.g. https://kyledeguire.github.io/ai-news-audio-feed")
    ap.add_argument("--audio-dir", default="audio", help="Relative audio directory (default: audio)")
    ap.add_argument("--feed", default="feed.xml", help="Feed output path (default: feed.xml)")
    ap.add_argument("--show-title", required=True)
    ap.add_argument("--show-description", required=True)
    ap.add_argument("--language", default="en-us")
    ap.add_argument("--image", default="artwork/cover.jpg", help="Optional image path under site (default: artwork/cover.jpg)")
    ap.add_argument("--audio-file", default="", help="Optional explicit MP3 filename (in audio/). If omitted, pick newest.")
    args = ap.parse_args()

    repo_url = args.repo_url.rstrip("/")
    audio_dir = Path(args.audio_dir)
    feed_path = Path(args.feed)

    if args.audio_file:
        mp3 = audio_dir / args.audio_file
        if not mp3.exists():
            sys.exit(f"update_feed.py: audio file not found: {mp3}")
    else:
        mp3 = newest_mp3(audio_dir)

    mp3_name = mp3.name
    mp3_url = f"{repo_url}/audio/{mp3_name}"
    site_link = f"{repo_url}/"
    image_url = f"{repo_url}/{args.image}" if args.image else None

    # Dates & sizes
    pub_dt = parse_stamp_from_filename(mp3_name)
    enclosure_len = file_length_bytes(mp3)

    # Episode title from date (e.g., "AI Executive Brief — Mon, Sep 15, 2025")
    pretty_date = pub_dt.strftime("%a, %b %d, %Y")
    ep_title = f"AI Executive Brief — {pretty_date}"

    # GUID: use basename without extension
    guid = mp3_name.replace(".mp3", "")

    item_xml = build_item_xml(
        title=ep_title,
        link=site_link,
        guid=guid,
        pub_date=pub_dt,
        enclosure_url=mp3_url,
        enclosure_len=enclosure_len,
    )

    feed_xml = build_feed_xml(
        show_title=args.show_title,
        show_description=args.show_description,
        language=args.language,
        site_link=site_link,
        image_url=image_url,
        item_xml=item_xml,
    )

    feed_path.write_text(feed_xml, encoding="utf-8")
    print(f"Wrote feed -> {feed_path} (item: {mp3_name})")

if __name__ == "__main__":
    main()
