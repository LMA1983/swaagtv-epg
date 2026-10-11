#!/usr/bin/env python3
"""Build swaagtv.xml (XMLTV, multiple channels) from public daily listings.

Channels:
  swaagtv - Swaag TV (WPVN-DT3), from TV Passport
  nost    - The Nostalgia Network, from watchnost.com/schedule

Env vars (optional): SOURCE_TZ (TV Passport display zone, default America/New_York),
OUT_TZ (default America/Chicago), DAYS (default 14).
To add a channel, add a fetcher below and an entry in CHANNELS.
"""
import os, re, sys, time
from datetime import date, datetime, timedelta
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

SRC = ZoneInfo(os.environ.get("SOURCE_TZ", "America/New_York"))
OUT = ZoneInfo(os.environ.get("OUT_TZ", "America/Chicago"))
DAYS = int(os.environ.get("DAYS", "14"))
UA = {"User-Agent": "Mozilla/5.0 (personal EPG builder)"}
TIME_RE = re.compile(r"^(\d{1,2}:\d{2})\s*([AP]M)$", re.I)


def get_lines(html, drop=("script", "style", "nav", "header", "footer")):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(list(drop)):
        t.decompose()
    return [l for l in (x.strip() for x in soup.get_text("\n").split("\n")) if l]


def parse_blocks(lines, stop_re, skip_after_title=0):
    """Lines -> [(time, title, desc)]: a time line starts a block; next line is the title."""
    items, cur = [], None
    for line in lines:
        m = TIME_RE.match(line)
        if m:
            t = datetime.strptime(f"{m.group(1)} {m.group(2).upper()}", "%I:%M %p").time()
            cur = [t, None, [], 0]
            items.append(cur)
        elif cur is not None:
            if stop_re.match(line):
                break
            if cur[1] is None:
                cur[1] = line
            elif not cur[2] and re.fullmatch(r"\(\d{4}\)", line):
                cur[1] += " " + line
            elif cur[3] < skip_after_title:
                cur[3] += 1  # e.g. genre line
            else:
                cur[2].append(line)
    return [(t, title, " ".join(d)) for t, title, d, _ in items if title]


# ---- Swaag TV (TV Passport): pages run 6:00 AM -> 6:00 AM in SRC zone -------------
TVP = "https://www.tvpassport.com/tv-listings/stations/swaag-tv-wpvndt3-chicago-il/15288/{d}"
TVP_STOP = re.compile(r"^(Do not share my Personal Information|Quick Links)", re.I)


def fetch_swaag(days):
    per_day = {}
    for n in range(days):
        d = datetime.now(SRC).date() + timedelta(days=n)
        try:
            r = requests.get(TVP.format(d=d.isoformat()), timeout=30, headers=UA)
            r.raise_for_status()
            items = parse_blocks(get_lines(r.text), TVP_STOP)
            print(f"swaagtv {d}: {len(items)} programs")
            if items:
                per_day[d] = items
        except Exception as e:
            print(f"swaagtv {d}: failed ({e})", file=sys.stderr)
        time.sleep(2)
    events = []
    for d in sorted(per_day):
        cur, prev = d, None
        for t, title, desc in per_day[d]:
            if prev is not None and t < prev:
                cur += timedelta(days=1)  # passed midnight
            prev = t
            events.append((datetime.combine(cur, t, tzinfo=SRC), title, desc))
    end = None
    if per_day:
        last = max(per_day)
        end = datetime.combine(last + timedelta(days=1), datetime.min.time().replace(hour=6), tzinfo=SRC)
    return events, end


# ---- NOST (watchnost.com): each page is one calendar day in the requested zone ----
NOST = "https://watchnost.com/schedule/?date={d}&timezone={tz}"
NOST_STOP = re.compile(r"^We Love Movies", re.I)


def fetch_nost(days):
    events, end = [], None
    for n in range(days):
        d = datetime.now(OUT).date() + timedelta(days=n)
        off = datetime.combine(d, datetime.min.time().replace(hour=12), tzinfo=OUT).strftime("%z")
        tz = f"{off[:3]}:{off[3:]}"
        try:
            r = requests.get(NOST.format(d=d.isoformat(), tz=tz), timeout=30, headers=UA)
            r.raise_for_status()
            items = parse_blocks(get_lines(r.text), NOST_STOP, skip_after_title=1)  # skip genre line
            print(f"nost {d}: {len(items)} programs")
            for t, title, desc in items:
                events.append((datetime.combine(d, t, tzinfo=OUT), title, desc))
            if items:
                end = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=OUT)
        except Exception as e:
            print(f"nost {d}: failed ({e})", file=sys.stderr)
        time.sleep(2)
    return events, end


CHANNELS = [
    ("swaagtv", "SWAAGTV", fetch_swaag),
    ("nost", "NOST - The Nostalgia Network", fetch_nost),
]


def programmes(cid, events, end):
    fmt = lambda dt: dt.astimezone(OUT).strftime("%Y%m%d%H%M%S %z")
    events = sorted({e[0]: e for e in reversed(sorted(events, key=lambda e: e[0]))}.values(), key=lambda e: e[0])
    out = []
    for i, (start, title, desc) in enumerate(events):
        stop = events[i + 1][0] if i + 1 < len(events) else end
        if stop is None or stop <= start:
            continue
        out.append(f'  <programme start="{fmt(start)}" stop="{fmt(stop)}" channel="{cid}">')
        out.append(f"    <title>{escape(title)}</title>")
        if desc:
            out.append(f"    <desc>{escape(desc)}</desc>")
        out.append("  </programme>")
    return out


def main():
    heads, bodies = [], []
    for cid, name, fetch in CHANNELS:
        events, end = fetch(DAYS)
        if not events:
            print(f"{cid}: nothing fetched, skipping this run", file=sys.stderr)
            continue
        heads += [f'  <channel id="{cid}">', f"    <display-name>{escape(name)}</display-name>", "  </channel>"]
        bodies += programmes(cid, events, end)
    if not bodies:
        sys.exit("No listings fetched; leaving existing swaagtv.xml untouched.")
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="swaagtv-epg">'] + heads + bodies + ["</tv>"]
    with open("swaagtv.xml", "w", encoding="utf-8") as f:
        f.write("\n".join(xml) + "\n")
    print("Wrote swaagtv.xml")


if __name__ == "__main__":
    main()
