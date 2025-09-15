#!/usr/bin/env python3
import datetime
import email.utils
from pathlib import Path
import re
import sys

FEED = Path("feed.xml")

def httpdate(dt: datetime.datetime) -> str:
    # RFC 2822/5322 date for RSS (e.g., Mon, 15 Sep 2025 04:48:46 GMT)
    return email.utils.format_datetime(dt, usegmt=True)

def main():
    if not FEED.exists():
        print("feed.xml not found, aborting.", file=sys.stderr)
        sys.exit(1)

    text = FEED.read_text(encoding="utf-8")

    now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
    now_rfc2822 = httpdate(now)

    # 1) Update channel-level lastBuildDate (create if missing)
    if "<lastBuildDate>" in text:
        text = re.sub(r"<lastBuildDate>.*?</lastBuildDate>",
                      f"<lastBuildDate>{now_rfc2822}</lastBuildDate>",
                      text, flags=re.DOTALL)
    else:
        # Insert right before </channel> as a fallback
        text = re.sub(r"</channel>",
                      f"  <lastBuildDate>{now_rfc2822}</lastBuildDate>\n</channel>",
                      text, flags=re.DOTALL)

    # 2) Update the *latest item* pubDate.
    # We’ll assume the latest item is the first <item> block in the feed (your generator writes newest first).
    # Replace only the first pubDate in the first item.
    def bump_first_item_pubdate(m):
        item_block = m.group(0)
        if "<pubDate>" in item_block:
            item_block = re.sub(r"<pubDate>.*?</pubDate>",
                                f"<pubDate>{now_rfc2822}</pubDate>",
                                item_block, count=1, flags=re.DOTALL)
        else:
            # No pubDate? add one near the top of the item
            item_block = item_block.replace("<item>", f"<item>\n  <pubDate>{now_rfc2822}</pubDate>", 1)
        return item_block

    text_new, n = re.subn(r"<item>.*?</item>", bump_first_item_pubdate, text, count=1, flags=re.DOTALL)
    if n == 0:
        print("No <item> found in feed.xml, nothing to bump.", file=sys.stderr)
        sys.exit(0)

    FEED.write_text(text_new, encoding="utf-8")
    print("Bumped channel <lastBuildDate> and latest item <pubDate> to:", now_rfc2822)

if __name__ == "__main__":
    main()
