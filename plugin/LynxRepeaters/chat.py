# Lynx-Enigma2: BATC live chat, read only.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""The chat beside each stream on batc.org.uk/live, shown on the picture as
bubbles while you watch (Justin, 2 Nov 2026).

BATC's page (live-assets/batc-chat.js) joins socket.io 2.x at
https://batc.org.uk/live-chat/socket.io with query room=<stream name> and
hears "history" (on joining), "message" ({time, name, message}), "viewers"
and "nicks". Sending needs a nickname; Lynx only listens, so no login.
Whether a stream has chat comes from live-api/stream.php?name=<stream>
(chat_on "1").

Socket.io 2 runs over Engine.IO 3, which can work by plain HTTP requests
("polling"): one GET to open a session, then GETs that the server holds
until it has something to send, and a ping POSTed every pingInterval. With
b64=1 the packets come as text, "<length>:<packet>" one after another, the
length counted as JavaScript counts a string (UTF-16 units). That needs
nothing more than urllib, on Python 2.7 and 3.

No Enigma2 imports here, so it tests on any PC.
"""
from __future__ import absolute_import, division, print_function

import json
import re
import ssl
import threading
import time

try:
    from urllib.parse import quote                    # Python 3
    from urllib.request import HTTPCookieProcessor, Request, build_opener
    from http.cookiejar import CookieJar
except ImportError:                                   # Python 2
    from urllib import quote
    from urllib2 import HTTPCookieProcessor, Request, build_opener
    from cookielib import CookieJar

from .repeaters import _native

BASE = "https://batc.org.uk/live-chat/socket.io/"
STREAM_INFO = "https://batc.org.uk/live-api/stream.php?name=%s"
SHOW_S = 10                                # how long a bubble stays up (Justin)
EXTRA_S_PER_LINE = 1                       # and a second more for each line past two
_ROOM = re.compile(r"^[A-Za-z0-9_.-]+$")   # stream names, as streams.py checks them


# Viewers can hide a sender (Apple's rule for apps that show other people's
# messages; right for every Lynx). Kept beside the presets, outside the
# plugin folder, so updates keep it.
HIDDEN = "/etc/enigma2/lynx_chat_hidden.json"
REPORT_URL = "https://batc.org.uk/incident-report-form/"
REPORT_TEXT = "batc.org.uk/incident-report-form"
RECENT = 12                                # messages kept for the hide or report screen


def load_hidden(path=HIDDEN):
    """Hidden senders, as typed in the chat; compared without case."""
    try:
        with open(path) as f:
            names = json.load(f)
        return [_native(n) for n in names if isinstance(n, (type(u""), str)) and n.strip()]
    except (IOError, OSError, ValueError):
        return []


def save_hidden(names, path=HIDDEN):
    seen, keep = set(), []
    for n in names:                        # one of each, whatever the case
        if n.strip().lower() not in seen:
            seen.add(n.strip().lower())
            keep.append(n.strip())
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(keep, key=lambda n: n.lower()), f)
    import os
    os.rename(tmp, path)


def is_hidden(name, hidden):
    n = (name or "").strip().lower()
    return any(n == h.strip().lower() for h in hidden)


def js_len(text):
    """A string's length as JavaScript counts it: characters outside the
    Basic Multilingual Plane (emoji) count two."""
    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)


_ASTRAL = re.compile(u"[\U00010000-\U0010FFFF]") if len(u"\U00010000") == 1 else None


def decode_payload(text):
    """Engine.IO 3 text payload, "<n>:<packet><n>:<packet>...", to packets.
    Without emoji the lengths are plain character counts, so the packets
    are cut by slicing: the chat history on joining can be long, and a loop
    over every character keeps the box's GUI waiting (2 Nov 2026)."""
    if _ASTRAL is None or not _ASTRAL.search(text):
        out, i = [], 0
        while i < len(text):
            colon = text.find(":", i)
            if colon < 0 or not text[i:colon].isdigit():
                break
            n = int(text[i:colon])
            out.append(text[colon + 1:colon + 1 + n])
            i = colon + 1 + n
        return out
    out, i = [], 0
    while i < len(text):
        colon = text.find(":", i)
        if colon < 0 or not text[i:colon].isdigit():
            break
        want, j = int(text[i:colon]), colon + 1
        k, got = j, 0
        while k < len(text) and got < want:
            got += 2 if ord(text[k]) > 0xFFFF else 1
            k += 1
        out.append(text[j:k])
        i = k
    return out


def encode_payload(packets):
    return "".join("%d:%s" % (js_len(p), p) for p in packets)


def events(packets):
    """Socket.io events in the packets: (name, data) for each "42[...]"."""
    for p in packets:
        if not p.startswith("42"):
            continue
        try:
            body = json.loads(p[2:])
        except ValueError:
            continue
        if isinstance(body, list) and body:
            yield body[0], (body[1] if len(body) > 1 else None)


def message(data):
    """A chat message as (name, text, local "HH:MM"), or None."""
    if not isinstance(data, dict):
        return None
    name = (data.get("name") or "").strip()
    text = " ".join((data.get("message") or "").split())
    if not name or not text:
        return None
    return _native(name)[:20], _native(text)[:400], clock(data.get("time"))


def clock(iso):
    """"2026-11-01T18:35:12.345Z" (UTC) as local "18:35"; now if unreadable."""
    try:
        import calendar
        t = calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        t = time.time()
    return time.strftime("%H:%M", time.localtime(t))


def show_for(lines):
    return SHOW_S + EXTRA_S_PER_LINE * max(0, lines - 2)


def _open(opener, req, timeout):
    """As streams.fetch: without checking BATC's certificate only if the box
    has no certificates to check it against."""
    try:
        return opener.open(req, timeout=timeout).read()
    except Exception as e:
        if "CERTIFICATE" not in str(e).upper() or not hasattr(ssl, "_create_unverified_context"):
            raise
    try:
        from urllib.request import HTTPSHandler       # Python 3
    except ImportError:
        from urllib2 import HTTPSHandler
    handlers = [h for h in opener.handlers if isinstance(h, HTTPCookieProcessor)]
    plain = build_opener(HTTPSHandler(context=ssl._create_unverified_context()), *handlers)
    return plain.open(req, timeout=timeout).read()


def chat_on(room, timeout=10):
    """Whether BATC has chat switched on for this stream."""
    req = Request(STREAM_INFO % quote(room), headers={"User-Agent": "Lynx-Enigma2"})
    body = _open(build_opener(), req, timeout)
    d = json.loads(body.decode("utf-8"))
    return isinstance(d, dict) and str(d.get("chat_on")) == "1"


class Listener(object):
    """Follows one stream's chat in two threads (long-poll and ping) and calls
    heard(name, text, hhmm) for each new message, from its own thread: the
    caller hands it on to Enigma2's. History on joining is not shown, nor
    anything said before this listener started."""

    RETRY_S = 20

    def __init__(self, room, heard, log=lambda text: None):
        if not _ROOM.match(room or ""):
            raise ValueError("bad stream name")
        self.room, self.heard, self.log = room, heard, log
        self.running = False
        self.sid = None
        self.ping_s = 25

    def start(self):
        self.running = True
        t = threading.Thread(target=self._run)
        t.daemon = True
        t.start()

    def stop(self):
        """Stops listening and, politely, tells BATC the session is over."""
        self.running = False
        if self.sid:
            def bye(sid=self.sid):
                try:
                    self._post(["1"])
                except Exception:
                    pass
            t = threading.Thread(target=bye)
            t.daemon = True
            t.start()

    def _url(self):
        u = BASE + "?EIO=3&transport=polling&b64=1&room=%s&t=%d" % (quote(self.room), int(time.time() * 1000))
        return u + ("&sid=%s" % quote(self.sid) if self.sid else "")

    def _get(self, timeout):
        req = Request(self._url(), headers={"User-Agent": "Lynx-Enigma2"})
        return decode_payload(_open(self.opener, req, timeout).decode("utf-8"))

    def _post(self, packets):
        req = Request(self._url(), data=encode_payload(packets).encode("utf-8"),
                      headers={"User-Agent": "Lynx-Enigma2", "Content-Type": "text/plain;charset=UTF-8"})
        _open(self.opener, req, 15)

    def _run(self):
        try:
            if not chat_on(self.room):
                self.log("chat: none on %s" % self.room)
                return
        except Exception as e:
            self.log("chat: could not ask BATC about %s (%s); trying anyway" % (self.room, e))
        told = False
        while self.running:
            try:
                self._session()
            except Exception as e:
                if not told:
                    self.log("chat: %s: %s; trying again every %d s" % (self.room, e, self.RETRY_S))
                    told = True
            for _ in range(self.RETRY_S * 2):
                if not self.running:
                    return
                time.sleep(0.5)

    def _session(self):
        self.opener, self.sid = build_opener(HTTPCookieProcessor(CookieJar())), None
        opened = self._get(15)
        if not opened or not opened[0].startswith("0"):
            raise IOError("no session from BATC")
        hello = json.loads(opened[0][1:])
        self.sid = hello["sid"]
        self.ping_s = max(5, hello.get("pingInterval", 25000) / 1000.0)
        self.log("chat: following %s" % self.room)
        pinger = threading.Thread(target=self._ping)
        pinger.daemon = True
        pinger.start()
        packets = opened[1:]
        while self.running:
            for name, data in events(packets):
                if name == "message":
                    m = message(data)
                    if m and self.running:
                        self.heard(*m)
            if any(p.startswith("1") for p in packets):
                raise IOError("BATC closed the chat")
            packets = self._get(self.ping_s + 20)

    def _ping(self):
        sid = self.sid
        while self.running and self.sid == sid:
            time.sleep(self.ping_s)
            if not (self.running and self.sid == sid):
                return
            try:
                self._post(["2"])
            except Exception:
                return


if __name__ == "__main__":
    # A check by hand, on the box or a PC: prints one stream's new chat.
    #   cd /usr/lib/enigma2/python/Plugins/Extensions && python3 -m LynxRepeaters.chat gb3oo
    import sys
    room = sys.argv[1] if len(sys.argv) > 1 else "gb3oo"
    print("chat on %s: %s" % (room, chat_on(room)))
    say = lambda text: sys.stdout.write(text + "\n") or sys.stdout.flush()
    Listener(room, lambda n, t, h: say("%s %s: %s" % (h, n, t)), say).start()
    while True:
        time.sleep(1)
