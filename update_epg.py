#!/usr/bin/env python3
"""Build swaagtv.xml (XMLTV, multiple channels) from public daily listings.

Channels:
  swaagtv - Swaag TV (WPVN-DT3), from TV Passport
  nost    - The Nostalgia Network, from watchnost.com/schedule
  TVC.caribbean - Television Caribbean, weekly grid from tvcplus.net (edited by hand)
  ZIZ.tv - ZIZ TV (St. Kitts & Nevis), weekly grid from zizonline.com/tv/schedule (edited by hand)

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


# ---- Television Caribbean (TVC): weekly grid from tvcplus.net/programme-schedule ----
# The guide there is an image, so edit this by hand when it changes. Mon=0 ... Sun=6.
TVC_TZ = ZoneInfo("America/Puerto_Rico")  # Atlantic Standard Time (UTC-4, no DST)
TVC_WEEK = {d: [] for d in range(7)}


def _tvc(days, rows):
    for d in days:
        TVC_WEEK[d] += rows


CNW, SMN, CP = "Caribbean News World", "St. Maarten Newsdesk", "Caribbean Programming"
_tvc(range(7), [(0,0,CP),(6,0,"Morning Inspiration"),(12,0,CNW),(19,0,CNW),(23,0,CNW)])
_tvc(range(5), [(7,0,CNW),(8,0,"Island Tea"),(11,0,SMN),(13,0,"Caribbean Concert"),
                (15,0,"Sports"),(17,0,SMN)])
_tvc([0], [(10,0,"Just Friends"),(11,30,"Jamaica Magazine"),(17,30,"Jamaica Magazine"),
           (18,0,"Just Friends"),(20,0,"Insights"),(21,0,"Moms in Paradise"),(22,0,"Island Breese")])
_tvc([1], [(10,0,"Insights"),(11,30,"ECCB Connects"),(17,30,"ECCB Connects"),(18,0,"Insights"),
           (20,0,"Newsline 360"),(20,30,"On Location"),(21,0,"Let's Talk With Jess"),(22,0,"CAAG Top 10")])
_tvc([2], [(10,0,"Newsline 360"),(11,30,"TVC Special"),(17,30,"TVC Special"),(18,0,"Newsline 360"),
           (20,0,"Inside Football"),(20,30,"Sit, Sip and Chat"),(21,0,"Caribbean Concert")])
_tvc([3], [(10,0,"Inside Football"),(11,30,"All Access"),(17,30,"All Access"),(18,0,"Inside Football"),
           (20,0,"Main Event"),(21,0,"Let's Talk With Jess"),(22,0,"Island Breese")])
_tvc([4], [(10,0,"Main Event"),(11,30,"Inside Government"),(17,30,"Inside Government"),(18,0,"Main Event"),
           (20,0,"JIFE Music Show"),(21,0,"Caribbean Concert")])
_tvc([5], [(7,0,CNW),(8,0,"Moms in Paradise"),(9,0,"Insights"),(10,0,"All Access"),(11,0,"Island Breese"),
           (13,0,"Main Event"),(14,0,"JIFE Music Show"),(15,0,"Sports"),(17,0,"Island Breese"),
           (18,0,"JIFE Music Show"),(20,0,"Caribbean Concert"),(22,0,CP)])
_tvc([6], [(7,0,"Positive TV"),(9,0,"CAAG Top 10"),(10,0,"New Birth Service Live"),(11,30,"Positive TV"),
           (13,0,"Moms in Paradise"),(14,0,"JIFE Music Show"),(15,0,"Caribbean Inspiration"),
           (17,0,"Just Friends"),(18,0,"JIFE Music Show"),(20,0,"Caribbean Inspiration"),(22,30,CP)])


def fetch_tvc(days):
    start = datetime.now(TVC_TZ).date()
    events = []
    for n in range(days):
        d = start + timedelta(days=n)
        for h, m, title in sorted(TVC_WEEK[d.weekday()]):
            events.append((datetime(d.year, d.month, d.day, h, m, tzinfo=TVC_TZ), title, ""))
    end = datetime.combine(start + timedelta(days=days), datetime.min.time(), tzinfo=TVC_TZ)
    return events, end


# ---- ZIZ TV (St. Kitts & Nevis, Channel 5): weekly grid from zizonline.com/tv/schedule ----
# Times on that page are local (AST). Edit by hand when the page changes. Mon=0 ... Sun=6.
ZIZ_TZ = ZoneInfo("America/Puerto_Rico")  # Atlantic Standard Time (UTC-4, no DST)
ZIZ_WEEK = {d: [] for d in range(7)}


def _ziz(days, rows):
    for d in days:
        ZIZ_WEEK[d] += rows


_ziz(range(7), [(0,0,"Archive Classics","Footage from the ZIZ vault, back to the 1970s")])
_ziz(range(5), [(16,0,"Afternoon Line-Up","Community programming and features"),
                (17,0,"Community Spotlight","Stories from across the Federation"),
                (18,0,"Health Wise","The medical and wellness show"),
                (19,0,"ZIZ Evening News","The day's headlines, live"),
                (20,0,"Federation Focus","In-depth interviews and analysis"),
                (22,0,"Policing With You","Public safety with the Police Force")])
_ziz([0], [(21,0,"In-Focus","Live local show")])
_ziz([1], [(21,0,"Telecomms Talk & Action Sports","Live local show")])
_ziz([2], [(21,0,"The People's Show","Live local show")])
_ziz([3, 4], [(21,0,"Live Local Show","")])
_ziz([5, 6], [(16,0,"Weekend Features","Culture, events and island life"),
              (18,0,"Sports Roundup","Football, netball, cricket and more"),
              (19,0,"ZIZ Evening News","The weekend in review, live"),
              (20,0,"Culture & Community","Carnival, Culturama and village festivals"),
              (21,0,"Special Presentation","Local productions and features")])


def fetch_ziz(days):
    start = datetime.now(ZIZ_TZ).date()
    events = []
    for n in range(days):
        d = start + timedelta(days=n)
        for h, m, title, desc in sorted(ZIZ_WEEK[d.weekday()]):
            events.append((datetime(d.year, d.month, d.day, h, m, tzinfo=ZIZ_TZ), title, desc))
    end = datetime.combine(start + timedelta(days=days), datetime.min.time(), tzinfo=ZIZ_TZ)
    return events, end


CHANNELS = [
    ("swaagtv", "SWAAGTV", fetch_swaag),
    ("nost", "NOST - The Nostalgia Network", fetch_nost),
    ("TVC.caribbean", "Television Caribbean (TVC)", fetch_tvc),
    ("ZIZ.tv", "ZIZ TV (Channel 5)", fetch_ziz),
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
