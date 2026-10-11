#!/usr/bin/env python3
"""Build swaagtv.xml (XMLTV) from TV Passport's daily listings for Swaag TV (WPVN-DT3).

Run daily. Output: swaagtv.xml in the current directory.
Env vars (optional):
  SOURCE_TZ   time zone the listings page displays (default America/New_York)
  OUT_TZ      time zone written to the file (default America/Chicago)
  DAYS        how many days ahead to fetch (default 14)
"""
import os, re, sys, time
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://www.tvpassport.com/tv-listings/stations/swaag-tv-wpvndt3-chicago-il/15288/{d}"
SRC = ZoneInfo(os.environ.get("SOURCE_TZ", "America/New_York"))
OUT = ZoneInfo(os.environ.get("OUT_TZ", "America/Chicago"))
DAYS = int(os.environ.get("DAYS", "14"))
CHANNEL_ID = "swaagtv"
TIME_RE = re.compile(r"^(\d{1,2}:\d{2})\s*([AP]M)$", re.I)
STOP_RE = re.compile(r"^(Do not share my Personal Information|Quick Links)", re.I)
DAY_START_HOUR = 6  # listing pages run 6:00 AM -> 6:00 AM


def parse_day(html):
    """Return [(time_obj, title, desc)] in page order."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer"]):
        t.decompose()
    lines = [l.strip() for l in soup.get_text("\n").split("\n")]
    lines = [l for l in lines if l]
    items, cur = [], None
    for line in lines:
        m = TIME_RE.match(line)
        if m:
            t = datetime.strptime(f"{m.group(1)} {m.group(2).upper()}", "%I:%M %p").time()
            cur = [t, None, []]
            items.append(cur)
        elif cur is not None:
            if STOP_RE.match(line):
                break
            if cur[1] is None:
                cur[1] = line
            elif not cur[2] and re.fullmatch(r"\(\d{4}\)", line):
                cur[1] += " " + line  # keep the year with the movie title
            else:
                cur[2].append(line)
    return [(t, title, " ".join(d)) for t, title, d in items if title]


def fetch_day(d):
    r = requests.get(BASE.format(d=d.isoformat()), timeout=30,
                     headers={"User-Agent": "Mozilla/5.0 (personal EPG builder)"})
    r.raise_for_status()
    return parse_day(r.text)


def build_events(day_items):
    """day_items: {date: [(time,title,desc)]} -> sorted [(start_dt, title, desc)]"""
    events = []
    for d in sorted(day_items):
        cur, prev = d, None
        for t, title, desc in day_items[d]:
            if prev is not None and t < prev:
                cur += timedelta(days=1)  # passed midnight
            prev = t
            events.append((datetime.combine(cur, t, tzinfo=SRC), title, desc))
    events.sort(key=lambda e: e[0])
    # drop duplicate starts (keep first)
    out, seen = [], set()
    for e in events:
        if e[0] not in seen:
            seen.add(e[0]); out.append(e)
    return out


def write_xml(events, path="swaagtv.xml"):
    fmt = lambda dt: dt.astimezone(OUT).strftime("%Y%m%d%H%M%S %z")
    last_day = max(e[0] for e in events).date()
    end_of_data = datetime.combine(last_day, datetime.min.time().replace(hour=DAY_START_HOUR), tzinfo=SRC)
    if end_of_data <= events[-1][0]:
        end_of_data += timedelta(days=1)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="swaagtv-epg">',
             f'  <channel id="{CHANNEL_ID}">', '    <display-name>SWAAGTV</display-name>', '  </channel>']
    for i, (start, title, desc) in enumerate(events):
        stop = events[i + 1][0] if i + 1 < len(events) else end_of_data
        lines.append(f'  <programme start="{fmt(start)}" stop="{fmt(stop)}" channel="{CHANNEL_ID}">')
        lines.append(f"    <title>{escape(title)}</title>")
        if desc:
            lines.append(f"    <desc>{escape(desc)}</desc>")
        lines.append("  </programme>")
    lines.append("</tv>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    today = datetime.now(SRC).date()
    day_items = {}
    for n in range(DAYS):
        d = today + timedelta(days=n)
        try:
            items = fetch_day(d)
            if items:
                day_items[d] = items
                print(f"{d}: {len(items)} programs")
            else:
                print(f"{d}: no programs parsed", file=sys.stderr)
        except Exception as e:
            print(f"{d}: failed ({e})", file=sys.stderr)
        time.sleep(2)
    if not day_items:
        sys.exit("No listings fetched; leaving existing swaagtv.xml untouched.")
    write_xml(build_events(day_items))
    print("Wrote swaagtv.xml")


if __name__ == "__main__":
    main()
