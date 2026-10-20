#!/usr/bin/env python3
"""Builds a rolling 30-day XMLTV guide for NY 48 (WWON-TV) from its weekly schedule.

Schedule source: https://www.wonnewyork.net/channel-48-programming-schedeule
Run daily so the guide never runs out.
Usage:  python generate_ny48.py                     -> writes ny48_epg.xml
        python generate_ny48.py --merge FILE.xml     -> adds NY 48 into an existing guide Also checks whether the station's page
changed since last run (writes schedule.hash and sets changed=true for the workflow).
"""
import hashlib, os, re, sys, urllib.request
from datetime import datetime, timedelta, time
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

CHANNEL_ID = "WWON.ny48"
OUT_FILE = "ny48_epg.xml"
DAYS = 30
SCHEDULE_URL = "https://www.wonnewyork.net/channel-48-programming-schedeule"
HASH_FILE = "schedule.hash"
NY = ZoneInfo("America/New_York")

# ---- Weekly schedule (Mon=0 ... Sun=6). Edit here when the station changes it. ----
wk = {}
def add(days, hh, mm, title):
    for d in days:
        wk.setdefault(d, []).append((time(hh, mm), title))

MF, MW = [0, 1, 2, 3, 4], [0, 1, 2]
for h, m, t in [(2,0,"Late Movies & Late Late Movies"),(6,0,"The Early Show"),
    (10,0,"The Adventures of Champion"),(11,0,"Stories of the Century"),(12,0,"Sky Ring"),
    (13,0,"Meet Corliss Archer"),(14,0,"My Little Margie"),(15,0,"On the Buses"),
    (16,0,"Fenn Street Gang"),(17,0,"Special Branch"),(18,0,"N.Y.P.D."),(19,0,"Dragnet"),
    (23,58,"The Midnight Movie")]:
    add(MF, h, m, t)
add(MW, 20, 0, "Primetime Movie Showcases")
add(MW, 21, 30, "$9,000 Movie / The 10 O'Clock Movie")
add([0], 23, 0, "Super Mega Trivia Slam")
add([1], 23, 0, "The Andy Due Show")
add([2], 23, 0, "Late Night Boomin'")
add(MW, 23, 30, "The Chad & Bunny Show")
add([3], 20, 0, "Mistress Peace Theatre")
add([3], 21, 30, "Beware Theatre")
add([3], 23, 0, "W.O.N Theatre")
add([4], 20, 0, "Cemetery Cinema")
add([4], 22, 0, "Off Beat Cinema")
for h, m, t in [(2,0,"The Late Movie"),(4,0,"The Late Late Show"),(5,30,"The Early Show"),
    (7,0,"Nutty's Treehouse"),(8,0,"Cartoon Starcade"),(9,0,"Don's Breakfast Serials"),
    (11,0,"Movies or Sports (To Be Determined)"),(17,0,"American Pro Wrestling"),
    (18,0,"FLOW Wrestling"),(19,0,"Alley Fights"),(20,0,"Creature Features"),
    (22,0,"Lord BloodRah's Nerve Wrackin' Theatre"),(23,58,"Chiller Night Theatre")]:
    add([5], h, m, t)
for h, m, t in [(1,30,"Livingston Presents"),(3,0,"Creature Triple Features"),
    (9,0,"Cooking with Vlada"),(9,30,"Shatkin FIRST Down"),(10,0,"Off the Cuff with Craig Mitchell"),
    (11,0,"Sidewalks Entertainment"),(12,0,"The Neil Haley Show"),(13,0,"Passionate Living"),
    (14,0,"History Highway"),(15,0,"Upstaged"),(15,30,"The House on the Hill"),
    (16,0,"Baby Blues Art Presents"),(17,0,"Woodsongs TV Show"),(18,0,"One Step Beyond"),
    (19,0,"Project UFO"),(20,0,"Demented Features"),(22,0,"After Hours Cinema"),
    (23,30,"Cinema Insomnia with Mr. Lobo")]:
    add([6], h, m, t)

def build_slots():
    today = datetime.now(NY).replace(hour=0, minute=0, second=0, microsecond=0)
    start0 = today - timedelta(days=1)  # include yesterday so the overnight show spans midnight
    slots = []
    for i in range(DAYS + 2):
        d = start0 + timedelta(days=i)
        for t, title in sorted(wk[d.weekday()]):
            slots.append((datetime.combine(d.date(), t, tzinfo=NY), title))
    slots.sort(key=lambda x: x[0].timestamp())
    end_cut = today + timedelta(days=DAYS)
    fmt = lambda d: d.strftime("%Y%m%d%H%M%S %z")
    progs = []
    for (s, title), (e, _) in zip(slots, slots[1:]):
        if e <= today or s >= end_cut:
            continue
        p = ET.Element("programme", start=fmt(s), stop=fmt(e), channel=CHANNEL_ID)
        ET.SubElement(p, "title", lang="en").text = title
        progs.append(p)
    ch = ET.Element("channel", id=CHANNEL_ID)
    ET.SubElement(ch, "display-name").text = "NY 48 (WWON-TV)"
    ET.SubElement(ch, "display-name").text = "WWON-TV"
    return ch, progs

def write_tree(root, path):
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n")

def build(merge_into=None):
    ch, progs = build_slots()
    if merge_into:
        root = ET.parse(merge_into).getroot()
        # remove any earlier NY 48 data so reruns never duplicate it
        for el in list(root):
            if el.get("id") == CHANNEL_ID or el.get("channel") == CHANNEL_ID:
                root.remove(el)
        # XMLTV wants all <channel> elements before any <programme>
        last_ch = max((i for i, el in enumerate(root) if el.tag == "channel"), default=-1)
        root.insert(last_ch + 1, ch)
        for p in progs:
            root.append(p)
        write_tree(root, merge_into)
        print(f"merged {len(progs)} NY 48 programmes into {merge_into}")
    else:
        root = ET.Element("tv", {"generator-info-name": "ny48-epg",
            "source-info-name": "wonnewyork.net NY 48 Programming Schedule",
            "source-info-url": SCHEDULE_URL})
        root.append(ch)
        for p in progs:
            root.append(p)
        write_tree(root, OUT_FILE)
        print(f"wrote {OUT_FILE} ({len(progs)} programmes)")

def check_page():
    """Hash the station's schedule text; report whether it changed since last run."""
    try:
        req = urllib.request.Request(SCHEDULE_URL, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"could not fetch schedule page: {e}")
        return False
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"PROGRAMMING SCHEDULE.*?(?=Copyright)", text, flags=re.S)
    if not m:
        print("could not locate schedule text on page")
        return False
    digest = hashlib.sha256(m.group(0).encode()).hexdigest()
    old = open(HASH_FILE).read().strip() if os.path.exists(HASH_FILE) else ""
    open(HASH_FILE, "w").write(digest + "\n")
    return bool(old) and old != digest  # first run just records the hash

if __name__ == "__main__":
    merge = sys.argv[sys.argv.index('--merge') + 1] if '--merge' in sys.argv else None
    build(merge)
    changed = check_page()
    print(f"schedule_changed={'true' if changed else 'false'}")
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as f:
            f.write(f"schedule_changed={'true' if changed else 'false'}\n")
    sys.exit(0)
