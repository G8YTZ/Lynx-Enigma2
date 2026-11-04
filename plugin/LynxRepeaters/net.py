# Lynx-Enigma2: connecting to BATC and GitHub, IPv6 or IPv4.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""urllib, but quick to give up on an address that does not answer.

Found on Colin G4KLB's line (4 Nov 2026): BATC took exactly as long to
answer as Lynx would wait (15 s, then 30 s when that was raised), every
time. His box had an IPv6 route that went nowhere: Python tries BATC's IPv6
address first, waits the whole time-out for it, then connects over IPv4 at
once (ping -6 lost every packet; ping -4 answered in 9 ms). Every request
paid it, the chat's pings arrived too late and BATC dropped the session.
Browsers hide this ("happy eyeballs"). Here each address gets 3 s to
connect, and the address and family that worked are tried first after
that. Used for the chat, the BATC stream list and the update check.

No Enigma2 imports, so it tests on any PC.
"""
from __future__ import absolute_import, division, print_function

import socket
import ssl
import time

try:
    from urllib.request import HTTPSHandler, build_opener   # Python 3
    import http.client as _httplib
except ImportError:                                       # Python 2
    from urllib2 import HTTPSHandler, build_opener
    import httplib as _httplib

CONNECT_S = 3.0                  # per address, before trying the next
_LAST = [None, None]             # the address family, and address, that connected last
NOTES = []                       # for a log: what connecting found


def _name(fam):
    return "IPv6" if fam == getattr(socket, "AF_INET6", -1) else "IPv4"


def connect(host, port, timeout):
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    if _LAST[0] is not None:
        infos.sort(key=lambda a: (a[4] != _LAST[1], a[0] != _LAST[0]))
    last, failed = None, []
    for i, (fam, kind, proto, _canon, addr) in enumerate(infos):
        sock = socket.socket(fam, kind, proto)
        sock.settimeout(timeout if i == len(infos) - 1 else min(CONNECT_S, timeout))
        began = time.time()
        try:
            sock.connect(addr)
        except Exception as e:
            sock.close()
            last = e
            failed.append("%s %.0f s" % (_name(fam), time.time() - began))
            continue
        if failed and _LAST[0] != fam:
            NOTES.append("connected over %s after no answer over %s" % (_name(fam), ", ".join(failed)))
        _LAST[0], _LAST[1] = fam, addr
        sock.settimeout(timeout)
        return sock
    raise last or IOError("no address for %s" % host)


class _Connection(_httplib.HTTPSConnection):
    def connect(self):
        if getattr(self, "_tunnel_host", None):           # through a proxy: as usual
            return _httplib.HTTPSConnection.connect(self)
        timeout = self.timeout if isinstance(self.timeout, (int, float)) else 30
        sock = connect(self.host, self.port, timeout)
        context = getattr(self, "_context", None) or ssl.create_default_context()
        self.sock = context.wrap_socket(sock, server_hostname=self.host)


class Handler(HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Connection, req, context=getattr(self, "_context", None))


def opener(*handlers, **kw):
    """urllib's opener, with the connecting above. unverified=True does not
    check the server's certificate (for a box with no certificates)."""
    if kw.get("unverified") and hasattr(ssl, "_create_unverified_context"):
        return build_opener(Handler(context=ssl._create_unverified_context()), *handlers)
    return build_opener(Handler(), *handlers)


def read(req, timeout, opener_=None):
    """The body of a request, checking the certificate if the box can: only
    without certificates to check against does it fetch without."""
    opener_ = opener_ or opener()
    try:
        return opener_.open(req, timeout=timeout).read()
    except Exception as e:
        if "CERTIFICATE" not in str(e).upper() or not hasattr(ssl, "_create_unverified_context"):
            raise
    keep = [h for h in opener_.handlers if h.__class__.__name__ == "HTTPCookieProcessor"]
    return opener(*keep, unverified=True).open(req, timeout=timeout).read()
