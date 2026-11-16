#!/usr/bin/env python3
"""Generate wesn_epg.xml (XMLTV) for WESN TV, Trinidad.

Source: https://wesncc.com/home/wesn-tv-guide/ (weekday schedule only;
the page lists no weekend schedule). Edit SCHEDULE below if the page changes.

Each weekday is a "broadcast day" starting 06:00 and running to 06:00 the
next morning (the overnight lineup is listed under the same weekday column).
"""
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

CHANNEL_ID = "WESN.tt"
CHANNEL_NAME = "WESN TV"
TZ = timezone(timedelta(hours=-4))  # Trinidad: UTC-4, no DST
DAYS_AHEAD = 14
OUT_FILE = "wesn_epg.xml"

NEWS = "WESN News"
AMP = "AM Prime"
TP = "Talking Point"
F24 = "France 24"
FOS = "The Face of Sports"
TQ = "10 Questions with Andy Johnson"
SL = "Strictly Legal"
OO = "One on One"
PS = "Psyched"
WUD = "What's Up Doc (Season 3)"
CJ = "WE Comedy Jam"
LSS = "Long Story Short"


def day(a, b, c, d, e, f, g, h, i, j, k, rel):
    """Build one weekday's slots as (start 'HH:MM', title) in broadcast order."""
    return [
        ("06:00", NEWS), ("06:05", AMP), ("07:00", NEWS), ("07:05", AMP),
        ("07:30", F24), ("08:00", TP), ("09:00", NEWS), ("09:05", TP),
        ("09:30", F24), ("10:00", NEWS), ("10:05", a), ("10:30", b),
        ("11:00", NEWS), ("11:05", c), ("11:30", d), ("12:00", NEWS),
        ("12:05", e), ("13:00", NEWS), ("13:05", F24), ("14:00", NEWS),
        ("14:05", F24), ("14:30", FOS), ("16:00", NEWS), ("16:05", F24),
        ("16:30", f), ("17:00", NEWS), ("17:05", F24), ("17:30", g),
        ("18:00", NEWS), ("18:05", AMP), ("19:30", h), ("20:00", i),
        ("20:30", j), ("21:00", TP), ("22:30", FOS),
        ("00:00", AMP), ("01:30", F24), ("02:00", TP), ("03:30", FOS),
        ("05:00", k), ("05:30", rel),
    ]


# weekday index: 0=Mon ... 4=Fri
SCHEDULE = {
    0: day(TQ + " (Repeat)", F24, PS + " (Repeat)", F24, F24, F24,
           SL + " (Repeat)", PS, CJ, LSS, PS,
           "Religious Program: Joyful Mysteries"),
    1: day(SL + " (Repeat)", F24, F24, WUD, F24, F24,
           TQ, SL, WUD, F24, SL,
           "Religious Program: Sorrowful Mysteries"),
    2: day(OO, F24, F24, F24, F24, WUD,
           OO + " (Repeat)", OO, TQ, F24, OO,
           "Religious Program: Glorious Mysteries"),
    3: day(SL, SL, PS, F24, WUD + " (Repeat)", F24,
           PS + " (Repeat)", SL, PS, CJ, SL,
           "Religious Program: Luminous Mysteries"),
    4: day(TQ, F24, OO + " (Repeat)", F24, F24, F24,
           TQ + " (Repeat)", TQ, OO, LSS, TQ,
           "Religious Program: Joyful Mysteries"),
}


def fmt(dt):
    return dt.strftime("%Y%m%d%H%M%S") + " -0400"


def build_day(date):
    """Return [(start, stop, title)] for the broadcast day starting at `date`."""
    slots = SCHEDULE[date.weekday()]
    starts = []
    cur = datetime(date.year, date.month, date.day, tzinfo=TZ)
    prev_min = None
    for hhmm, title in slots:
        h, m = map(int, hhmm.split(":"))
        minutes = h * 60 + m
        if prev_min is not None and minutes < prev_min:
            cur += timedelta(days=1)  # rolled past midnight
        prev_min = minutes
        starts.append((cur.replace(hour=h, minute=m), title))
    end_of_day = starts[0][0] + timedelta(days=1)
    out = []
    for idx, (st, title) in enumerate(starts):
        stop = starts[idx + 1][0] if idx + 1 < len(starts) else end_of_day
        out.append((st, stop, title))
    return out


def main():
    today = datetime.now(TZ).date()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tv generator-info-name="generate_wesn.py">',
             f'  <channel id="{CHANNEL_ID}">',
             f'    <display-name>{CHANNEL_NAME}</display-name>',
             '  </channel>']
    for offset in range(-1, DAYS_AHEAD):
        d = today + timedelta(days=offset)
        if d.weekday() > 4:
            continue  # no weekend schedule published
        for st, stop, title in build_day(d):
            lines.append(
                f'  <programme start="{fmt(st)}" stop="{fmt(stop)}" '
                f'channel="{CHANNEL_ID}">')
            lines.append(f'    <title lang="en">{escape(title)}</title>')
            lines.append('  </programme>')
    lines.append('</tv>')
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT_FILE}")


if __name__ == "__main__":
    main()
