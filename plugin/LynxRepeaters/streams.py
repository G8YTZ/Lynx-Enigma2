# Lynx-Enigma2: BATC live streams.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""The BATC streamer's list of live streams, as Lynx Rx uses it: fetched
once an hour, kept on the box, turned into a "BATC Live" channel list and
matched to repeaters by callsign.

The streams play as RTMP through the box's own player (service type 4097,
GStreamer's rtmpsrc). Only the stream's name comes from the list; the
address is always rtmp://rtmp.batc.org.uk/live/<name>, so a list that has
been tampered with cannot send the box anywhere else.

No Enigma2 imports here, so it tests on any PC.
"""
from __future__ import absolute_import, division, print_function

import io
import json
import os
import re
import ssl
import time

try:
    from urllib.request import Request, urlopen      # Python 3
except ImportError:                                   # Python 2
    from urllib2 import Request, urlopen

from .repeaters import _native

API = "https://batc.org.uk/live-api/stream_list.php"
RTMP = "rtmp://rtmp.batc.org.uk/live/%s"
MAX_AGE_S = 3600
CACHE = "/etc/enigma2/lynx_streams.json"
BOUQUET = "userbouquet.lynx_batc.tv"
BOUQUET_DIR = "/etc/enigma2"
BOUQUET_TITLE = "BATC Live"

# Enigma2 service types for internet streams. 4097 is the image's own player
# (on HiSilicon boxes, HiSilicon's, which often misses the video of a live
# RTMP stream); 5002 and 5001 come with the ServiceApp add-on: exteplayer3
# (ffmpeg) and gstplayer (GStreamer).
PLAYERS = {"builtin": 4097, "exteplayer3": 5002, "gstplayer": 5001}
SERVICEAPP = "/usr/lib/enigma2/python/Plugins/SystemPlugins/ServiceApp"
EXTEPLAYER3 = "/usr/bin/exteplayer3"


GSTPLAYER = "/usr/bin/gstplayer"
PLAYER_NAMES = {4097: "the box's own player", 5001: "gstplayer", 5002: "exteplayer3"}


def player_chain(choice="auto"):
    """Service types to try in turn. auto: gstplayer, then exteplayer3,
    where ServiceApp has them, and the box's own player last (on the H11S
    most BATC streams give it sound only; Justin, 20 Oct 2026). A named
    player alone otherwise."""
    if choice in PLAYERS:
        return [PLAYERS[choice]]
    chain = []
    if os.path.isdir(SERVICEAPP):
        if os.path.exists(GSTPLAYER):
            chain.append(PLAYERS["gstplayer"])
        if os.path.exists(EXTEPLAYER3):
            chain.append(PLAYERS["exteplayer3"])
    return chain + [PLAYERS["builtin"]]


def player_type(choice="auto"):
    """The first player to try: what the BATC Live channel list uses."""
    return player_chain(choice)[0]


_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def parse(data):
    """Live, listed streams from the API's JSON (a dict of categories, each
    a list of streams), repeaters first, then by name."""
    out, seen = [], set()
    for streams in data.values() if isinstance(data, dict) else ():
        if not isinstance(streams, list):
            continue
        for s in streams:
            if not isinstance(s, dict) or not s.get("active"):
                continue
            if str(s.get("stream_listed")) != "1":
                continue
            title = (s.get("stream_title") or "").strip()
            key = (s.get("stream_output_url") or "").strip()
            if not title or not _KEY.match(key) or key.lower() in seen:
                continue
            seen.add(key.lower())
            out.append({"name": title, "key": key, "url": RTMP % key,
                        "repeater": str(s.get("stream_type_repeater", "0")) == "1"})
    out.sort(key=lambda x: (not x["repeater"], x["name"].lower()))
    return out


def for_call(streams, call):
    """The live stream for a repeater, matched on the stream's name (gb3oo),
    or None."""
    call = call.lower()
    for s in streams:
        if s["key"].lower() == call:
            return s
    for s in streams:
        k = s["key"].lower()
        if k.startswith(call) and not k[len(call):len(call) + 1].isalnum():
            return s
    return None


_CALL = re.compile(r"^[A-Z0-9]{1,3}[0-9][A-Z0-9]{1,4}$")


def stream_only(streams, listed_calls):
    """Streams BATC marks as repeaters that match no repeater on the list
    (DB0OZ Bremen, say): one entry each, callsign and place split from the
    stream's title where it starts with a callsign."""
    listed = [c.lower() for c in listed_calls]
    out = []
    for s in streams:
        if not s.get("repeater"):
            continue
        if any(for_call([s], c) for c in listed):
            continue
        words = s["name"].split(None, 1)
        if words and _CALL.match(words[0].upper()):
            call, town = words[0].upper(), (words[1] if len(words) > 1 else "")
        else:
            call, town = s["name"], ""
        out.append({"call": call, "town": town, "stream": s})
    out.sort(key=lambda x: x["call"])
    return out


def service_ref(stream, stype=4097):
    """An Enigma2 service for a stream: the player's service type, URL with
    its colon escaped, then the name to show."""
    name = stream["name"].replace(":", " ").replace("\n", " ")
    return "%d:0:1:0:0:0:0:0:0:0:%s:%s" % (stype, stream["url"].replace(":", "%3a"), name)


def bouquet_text(streams, stype=4097):
    lines = ["#NAME %s" % BOUQUET_TITLE]
    for s in streams:
        lines.append("#SERVICE %s" % service_ref(s, stype))
        lines.append("#DESCRIPTION %s" % s["name"].replace("\n", " "))
    return "\n".join(lines) + "\n"


def bouquet_line():
    return '#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "%s" ORDER BY bouquet' % BOUQUET


def with_bouquet(bouquets_tv):
    """bouquets.tv with ours added at the end, or None if it is there."""
    if BOUQUET in bouquets_tv:
        return None
    return bouquets_tv.rstrip("\n") + "\n" + bouquet_line() + "\n"


def fetch(timeout=15):
    """The live list from BATC. If the box has no certificates to check
    BATC's against, it fetches without checking: only stream names are
    used from the list, so the worst a forged list could do is name
    streams that do not exist."""
    req = Request(API, headers={"User-Agent": "Lynx-Enigma2"})
    try:
        body = urlopen(req, timeout=timeout).read()
    except Exception as e:
        if "CERTIFICATE" not in str(e).upper() or not hasattr(ssl, "_create_unverified_context"):
            raise
        body = urlopen(req, timeout=timeout, context=ssl._create_unverified_context()).read()
    return parse(_native(json.loads(body.decode("utf-8"))))


def save(streams, path=CACHE, now=None):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        text = json.dumps({"fetched": now or time.time(), "streams": streams}, indent=1)
        f.write(text if isinstance(text, type(u"")) else text.decode("utf-8"))
    os.rename(tmp, path)


def load(path=CACHE):
    """(streams, when fetched) from the box's copy, or ([], 0)."""
    try:
        with io.open(path, encoding="utf-8") as f:
            d = _native(json.load(f))
        return d.get("streams", []), d.get("fetched", 0)
    except (IOError, OSError, ValueError):
        return [], 0


def write_bouquet(streams, folder=BOUQUET_DIR, stype=4097):
    """Write the BATC Live channel list and make sure the TV list includes it.
    Returns True if anything changed (the box then reloads its bouquets)."""
    path = os.path.join(folder, BOUQUET)
    text = bouquet_text(streams, stype)
    old = None
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as f:
            old = f.read()
    changed = False
    if old != text:
        with io.open(path, "w", encoding="utf-8") as f:
            f.write(text if isinstance(text, type(u"")) else text.decode("utf-8"))
        changed = True
    tv = os.path.join(folder, "bouquets.tv")
    if os.path.exists(tv):
        with io.open(tv, encoding="utf-8") as f:
            new = with_bouquet(f.read())
        if new is not None:
            with io.open(tv, "w", encoding="utf-8") as f:
                f.write(new)
            changed = True
    return changed
