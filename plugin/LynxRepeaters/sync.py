# Lynx-Enigma2: keep the BATC live stream list up to date.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Fetches the BATC list an hour after the last fetch, starting a minute
after boot. The network call runs in a worker thread so the GUI never
waits on it; writing the channel list and reloading it happen back on
Enigma2's own thread. If BATC cannot be reached the last list stays."""
from __future__ import absolute_import, division, print_function

import os
import subprocess
import threading
import time

from . import streams
from .tuning import _timer

FIRST_DELAY_MS = 60 * 1000
POLL_MS = 1000


# A box with no battery-backed clock starts at its image's build date after
# a power cut, and a repeater-only box never sees satellite time. HTTPS to
# BATC fails until the clock is right, so set it once if it is plainly wrong.
SANE_YEAR = 2025
NTP_SERVER = "pool.ntp.org"
NTPDATE = ("/usr/sbin/ntpdate", "/usr/bin/ntpdate", "/sbin/ntpdate")


def fix_clock():
    if time.localtime().tm_year >= SANE_YEAR:
        return False
    for exe in NTPDATE:
        if os.path.exists(exe):
            try:
                rc = subprocess.call([exe, "-b", NTP_SERVER])
                print("[LynxRepeaters] clock was wrong; %s gave %d, now %s" % (exe, rc, time.ctime()))
                return rc == 0
            except Exception as e:
                print("[LynxRepeaters] clock: %s" % e)
    return False


class StreamSync(object):
    instance = None

    def __init__(self):
        StreamSync.instance = self
        self.streams, self.fetched = streams.load()
        self.listeners = []            # called with no arguments after an update
        self._result = None
        self._worker = None
        self.timer, self._tc = _timer(self.due)
        self.poll, self._pc = _timer(self._check)

    @staticmethod
    def player():
        try:
            from .screens import cfg
            return cfg.player.value
        except Exception:
            return "auto"

    def rewrite_bouquet(self):
        """After the player setting changes: same streams, new service type."""
        try:
            if streams.write_bouquet(self.streams, stype=streams.player_type(self.player())):
                from enigma import eDVBDB
                eDVBDB.getInstance().reloadBouquets()
        except Exception as e:
            print("[LynxRepeaters] BATC channel list: %s" % e)

    def start(self, delay_ms=FIRST_DELAY_MS):
        self.timer.start(delay_ms, True)

    def stale(self):
        age = time.time() - self.fetched
        return age < 0 or age > streams.MAX_AGE_S      # from the "future": the clock is wrong

    def due(self):
        """Fetch now if the list is an hour old; check again in an hour."""
        if self.stale():
            self.refresh()
        self.timer.start(streams.MAX_AGE_S * 1000, True)

    def refresh(self):
        if self._worker and self._worker.is_alive():
            return
        self._result = None
        self._worker = threading.Thread(target=self._fetch)
        self._worker.daemon = True
        self._worker.start()
        self.poll.start(POLL_MS, True)

    def _fetch(self):                  # worker thread: no Enigma2 calls here
        fix_clock()
        try:
            self._result = ("ok", streams.fetch())
        except Exception as e:
            self._result = ("error", e)

    def _check(self):                  # Enigma2's thread
        if self._result is None:
            self.poll.start(POLL_MS, True)
            return
        kind, value = self._result
        self._result = None
        if kind == "error":
            print("[LynxRepeaters] BATC stream list: %s" % value)
            return
        self.streams, self.fetched = value, time.time()
        print("[LynxRepeaters] BATC stream list: %d live" % len(value))
        try:
            streams.save(value)
            if streams.write_bouquet(value, stype=streams.player_type(self.player())):
                from enigma import eDVBDB
                eDVBDB.getInstance().reloadBouquets()
        except Exception as e:
            print("[LynxRepeaters] BATC channel list: %s" % e)
        for fn in list(self.listeners):
            try:
                fn()
            except Exception as e:
                print("[LynxRepeaters] stream listener: %s" % e)


def get():
    return StreamSync.instance or StreamSync()
