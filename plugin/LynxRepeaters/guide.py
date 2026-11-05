# -*- coding: utf-8 -*-
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
"""guide.py - the programme guide for what Lynx is playing.

A repeater that sends an EPG (GB3OO's Lynx-Tx does: now, next and 8 days,
from its Companion schedule) arrives in two ways:

  - Enigma2's EPG cache, which holds the whole schedule. It reads the
    stream for a while after a channel is tuned, then about hourly, so a
    guide that went on air while the channel was already playing is not
    there until the next look or a retune.
  - The live now and next, read straight from the stream by the service
    itself: always there while a guide is sent (the info bar uses it).

The guide shows the cache when it has anything for this service, and
otherwise the live now and next with a line saying the rest is coming.

No Enigma2 imports at module level: the arithmetic is tested off the box.
"""
from __future__ import absolute_import, division, print_function

import time

FIELDS = "IBDTSE"        # event id, begin, duration, title, short, extended


def from_cache(ref, now=None):
    """Every event Enigma2 holds for ref (a service reference string), from
    the one running now onwards, as dicts. [] if none or no cache."""
    now = int(now or time.time())
    try:
        from enigma import eEPGCache
        found = eEPGCache.getInstance().lookupEvent([FIELDS, (ref, 0, -1, -1)]) or []
    except Exception:
        return []
    return tidy([event(*t) for t in found if t and len(t) >= 6], now)


def from_live(service, now=None):
    """The now and next the stream itself carries, from the playing
    service's own information. [] if it has none."""
    now = int(now or time.time())
    out = []
    try:
        info = service and service.info()
        for i in (0, 1):
            e = info and info.getEvent(i)
            if e:
                out.append(event(e.getEventId(), e.getBeginTime(), e.getDuration(),
                                 e.getEventName(), e.getShortDescription(),
                                 e.getExtendedDescription()))
    except Exception:
        return []
    return tidy(out, now)


def event(eid, begin, duration, title, short="", extended=""):
    return {"id": eid, "begin": int(begin or 0), "duration": int(duration or 0),
            "title": (title or "").strip(), "short": (short or "").strip(),
            "extended": (extended or "").strip()}


def tidy(events, now):
    """Sorted by start, nothing already over, nothing without a title or a
    start, no event twice."""
    seen, out = set(), []
    for e in sorted(events, key=lambda e: e["begin"]):
        key = (e["begin"], e["title"])
        if not e["title"] or e["begin"] <= 0 or e["begin"] + e["duration"] <= now or key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def is_now(e, now):
    return e["begin"] <= now < e["begin"] + e["duration"]


def row(e, now, localtime=time.localtime):
    """One line of the guide: day, start, title, and the length when it is
    not an hour; "now" with the minutes left for the one running."""
    t = localtime(e["begin"])
    day = time.strftime("%a", t)
    hhmm = time.strftime("%H:%M", t)
    mins = e["duration"] // 60
    if is_now(e, now):
        left = max(0, (e["begin"] + e["duration"] - now + 59) // 60)
        tail = "  (now, %d min left)" % left
    else:
        tail = "" if mins == 60 else "  (%d min)" % mins
    return "%s %s   %s%s" % (day, hhmm, e["title"], tail)


def columns(e, now, localtime=time.localtime):
    """The guide's three columns: when, title, and a note (minutes left for
    the one on now, the length when it is not an hour)."""
    t = localtime(e["begin"])
    when = "%s %s" % (time.strftime("%a", t), time.strftime("%H:%M", t))
    mins = e["duration"] // 60
    if is_now(e, now):
        note = "now, %d min left" % max(0, (e["begin"] + e["duration"] - now + 59) // 60)
    else:
        note = "" if mins == 60 else "%d min" % mins
    return when, e["title"], note


def description(e):
    """The selected event's words, as much as the stream gives."""
    parts = [p for p in (e.get("short"), e.get("extended")) if p]
    if parts and len(parts) == 2 and parts[1].startswith(parts[0]):
        parts = parts[1:]
    return "\n\n".join(parts)


def clip(text, n):
    """At most n characters, cut at a word with "..." (bytes on Python 2
    are UTF-8: cut as characters, never mid-letter)."""
    was_bytes = not isinstance(text, type(u""))
    u = text.decode("utf-8", "replace") if was_bytes else text
    if len(u) > n:
        cut = u[:n - 3]
        if " " in cut[n // 2:]:
            cut = cut.rsplit(" ", 1)[0]
        u = cut.rstrip(" ,.;:-") + u"..."
    return u.encode("utf-8") if was_bytes else u


def now_key(events, now):
    """What is on now, as something to compare from one second to the next
    (the Lynx bar pops up when it changes); None without a guide."""
    for e in events:
        if is_now(e, now):
            return (e["begin"], e["title"])
    return None


def now_next(events, now, localtime=time.localtime, n=30):
    """The Lynx bar's guide line: "Now: <title>  19:00-20:00   Next:
    <title>  20:00", either half alone if that is all there is; "" without
    a guide."""
    hhmm = lambda t: time.strftime("%H:%M", localtime(t))
    cur = [e for e in events if is_now(e, now)]
    parts = []
    after = now
    if cur:
        e = cur[0]
        end = e["begin"] + e["duration"]
        parts.append("Now: %s  %s-%s" % (clip(e["title"], n), hhmm(e["begin"]), hhmm(end)))
        after = end
    later = [e for e in events if e["begin"] >= after and not is_now(e, now)]
    if later:
        parts.append("Next: %s  %s" % (clip(later[0]["title"], n), hhmm(later[0]["begin"])))
    return "   ".join(parts)
