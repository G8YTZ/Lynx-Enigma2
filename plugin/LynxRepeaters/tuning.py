# Lynx-Enigma2: tune a repeater and find its programme.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Repeaters do not publish their service IDs, so Lynx does not keep
channels for them. To watch one it scans that single transponder (as the
box's own manual scan would, but with no other transponders), notes the
services the scan finds and plays the first TV one. The scan adds them to
the box's service list like any other; nothing else in the list is touched.

With an unknown symbol rate (or when asked to hunt) it tries the common
rates in turn until one gives a service.
"""
from __future__ import absolute_import, division, print_function

from .log import log

import os
import subprocess
import sys
from numbers import Integral

from enigma import eComponentScan, eDVBFrontendParametersSatellite, eServiceReference, eTimer

from . import repeaters

try:
    _
except NameError:          # Enigma2 installs _ as a builtin; this is for tests
    def _(s):
        return s

S = eDVBFrontendParametersSatellite

# Keep everything already in the service list; replace what was known on
# this one transponder (a repeater may have changed its SID since last time).
SCAN_FLAGS = (getattr(eComponentScan, "scanDontRemoveUnscanned", 16)
              | getattr(eComponentScan, "scanRemoveServices", 4))

# A scan normally finishes in a second or two, or a few more seconds when
# there is nothing to lock to. This is the backstop.
SCAN_TIMEOUT_MS = 20000

# After a stream (gstplayer or exteplayer3, separate programs on the box)
# the video decoder is still held for a moment after the service stops; tune
# too soon and the on-air picture stays frozen on the stream's last frame
# (20 Oct 2026, OpenATV 8). So wait this long before tuning after a stream.
STREAM_RELEASE_MS = 1500

# ServiceApp's player programs. On OpenATV 8 stopping the service can leave
# gstplayer2 running and holding the video decoder (seen 20 Oct 2026: on-air
# sound, no picture, gstplayer2 still running minutes later), so Lynx ends
# any that are left before it tunes on air.
STREAM_PLAYERS = ("gstplayer2", "gstplayer", "exteplayer3")


def end_stream_players():
    """End any stream player program still running. True if one was."""
    found = False
    for name in STREAM_PLAYERS:
        try:
            if subprocess.call(["killall", name], stdout=_DEVNULL, stderr=_DEVNULL) == 0:
                found = True
                log("ended a leftover %s" % name)
        except OSError:
            pass                       # no killall here: nothing more to do
    return found

_DEVNULL = open(os.devnull, "w")

# DVB service types that carry video (SD, MPEG-2 HD, H.264 SD/HD, HEVC).
VIDEO_TYPES = {0x01, 0x11, 0x16, 0x19, 0x1F, 0x20}
RADIO_TYPES = {0x02, 0x0A}


def _connect(signal, fn):
    """Connect to an Enigma2 signal on both old (list) and new (connect) images.
    Keep what this returns: dropping it disconnects on new images."""
    if hasattr(signal, "connect"):
        return signal.connect(fn)
    signal.get().append(fn)
    return (signal, fn)


def _disconnect(conn):
    if isinstance(conn, tuple):
        try:
            conn[0].get().remove(conn[1])
        except (ValueError, AttributeError):
            pass


def _timer(fn):
    t = eTimer()
    return t, _connect(t.timeout if hasattr(t, "timeout") else t.callback, fn)


def _set(p, name, value):
    try:
        setattr(p, name, value)
    except (AttributeError, TypeError):
        pass                          # field missing on this image: leave it


# What to tell someone whose satellite tuner is not set up (OpenATV 8's
# first-boot wizard left tuner A "not configured" on 20 Oct 2026).
NO_TUNER = "no tuner set up: Menu, Setup, Tuner Configuration, Tuner A: Simple, Astra 19.2E"


def find_tuner(orbpos=repeaters.BOX_ORBPOS):
    """The first satellite tuner set up for the box's LNB position; None if
    the box has tuners but none is set up for it; 0 if Lynx cannot tell."""
    try:
        from Components.NimManager import nimmanager
    except Exception as e:
        log("tuner search: %s" % e)
        return 0
    try:
        for slot in nimmanager.nim_slots:
            if not slot.isCompatible("DVB-S"):
                continue
            if any(sat[0] == orbpos for sat in nimmanager.getSatListForNim(slot.slot)):
                return slot.slot
    except Exception as e:            # an odd tuner set-up must not stop us
        log("tuner search: %s" % e)
        return 0
    return None


def transponder(entry, sr_ks, supply_v="13"):
    """eDVBFrontendParametersSatellite for one output at one symbol rate.
    The polarisation sets the LNB supply: vertical 13 V, horizontal 18 V."""
    out = entry["output"]
    p = S()
    p.frequency = entry["box_khz"]
    p.symbol_rate = int(sr_ks) * 1000
    p.polarisation = (getattr(S, "Polarisation_Horizontal", 0) if str(supply_v) == "18"
                      else getattr(S, "Polarisation_Vertical", 1))
    p.fec = getattr(S, "FEC_Auto", 0)
    p.inversion = getattr(S, "Inversion_Unknown", 2)
    p.orbital_position = repeaters.BOX_ORBPOS
    p.system = (getattr(S, "System_DVB_S", 0) if out.get("mode") == "DVB-S"
                else getattr(S, "System_DVB_S2", 1))
    p.modulation = getattr(S, "Modulation_QPSK", 1)
    p.rolloff = getattr(S, "RollOff_alpha_0_35", 0)
    p.pilot = getattr(S, "Pilot_Unknown", 2)
    _set(p, "is_id", getattr(S, "No_Stream_Id_Filter", -1))
    _set(p, "pls_mode", getattr(S, "PLS_Gold", 1))
    _set(p, "pls_code", getattr(S, "PLS_Default_Gold_Code", 0))
    _set(p, "t2mi_plp_id", getattr(S, "No_T2MI_PLP_Id", -1))
    _set(p, "t2mi_pid", getattr(S, "T2MI_Default_Pid", 4096))
    return p


def symbol_rates(entry, hunt=False):
    """Symbol rates to try: the listed one, or every common one."""
    listed = entry["output"].get("sr_ks")
    rates = [] if not listed else [listed]
    if hunt or not listed:
        rates += [r for r in repeaters.COMMON_SR_KS if r != listed and r >= repeaters.MIN_SR_KS]
    return rates


def playing_stream(session):
    """Whether what is playing now is an internet stream (not a DVB service,
    whose references start with 1)."""
    try:
        nav = session.nav
        get = getattr(nav, "getCurrentlyPlayingServiceOrGroup", None) or nav.getCurrentlyPlayingServiceReference
        ref = get()
        return bool(ref) and ref.toString().split(":", 1)[0] != "1"
    except Exception:
        return False


def service_type(ref):
    try:
        return int(ref.split(":")[2], 16)
    except (IndexError, ValueError):
        return -1


def pick_service(refs):
    """The first TV service; failing that anything but radio; else the first."""
    for r in refs:
        if service_type(r) in VIDEO_TYPES:
            return r
    for r in refs:
        if service_type(r) not in RADIO_TYPES:
            return r
    return refs[0] if refs else None


class RepeaterTuner:
    """Tunes one output, trying symbol rates in turn.

    progress(text) is called as each rate is tried. done(ref, sr_ks, error)
    is called once: ref is the eServiceReference string now playing, or None
    with error saying why."""

    def __init__(self, session, progress, done):
        self.session, self.progress, self.done = session, progress, done
        self.scan = None
        self._conns = []
        self.watchdog, self._wd = _timer(self._timeout)
        self.later, self._lt = _timer(self._after_scan)
        self.settle, self._sl = _timer(self._next)
        self.busy = False

    def tune(self, entry, supply_v="13", hunt=False):
        self.entry, self.supply_v = entry, supply_v
        self.rates = symbol_rates(entry, hunt)
        self.tried = []
        self.feid = find_tuner()
        self.sr = None
        if self.feid is None:
            # Say what is wrong rather than report no signal at every rate.
            return self.done(None, None, NO_TUNER)
        self.busy = True
        was_stream = playing_stream(self.session)
        self.session.nav.stopService()      # free the tuner for the scan
        if end_stream_players():
            was_stream = True              # give the decoder time to come free
        if was_stream:
            self.progress(_("Tuning %s: letting the stream go") % entry["call"])
            self.settle.start(STREAM_RELEASE_MS, True)
        else:
            self._next()

    def cancel(self):
        self.settle.stop()
        if self.busy:
            self._stop_scan()
            self.busy = False

    # One symbol rate after another

    def _next(self):
        self._stop_scan()
        if not self.busy:
            return
        if not self.rates:
            return self._finish(None, _("No signal at %s kS/s") % ", ".join(str(r) for r in self.tried))
        self.sr = self.rates.pop(0)
        self.tried.append(self.sr)
        out = self.entry["output"]
        self.progress(_("Tuning %s: %g MHz, %d kS/s") % (self.entry["call"], out["freq_mhz"], self.sr))
        self.found = []
        self.scan = eComponentScan()
        self._conns = [_connect(self.scan.statusChanged, self._status),
                       _connect(self.scan.newService, self._new_service)]
        self.scan.addInitial(transponder(self.entry, self.sr, self.supply_v))
        if self.scan.start(self.feid, SCAN_FLAGS) < 0:
            return self._finish(None, _("The tuner is busy (is the box recording?)"))
        self.watchdog.start(SCAN_TIMEOUT_MS, True)

    def _new_service(self):
        if self.scan:
            ref = self.scan.getLastServiceRef()
            if ref and ref not in self.found:
                self.found.append(ref)
                log("found %s %s" % (ref, self.scan.getLastServiceName()))

    def _status(self):
        # Never tear the scan down from inside its own signal: do it next tick.
        if self.scan and self.scan.isDone():
            self.later.start(0, True)

    def _timeout(self):
        log("scan timed out at %d kS/s" % self.sr)
        self._after_scan()

    def _after_scan(self):
        if not self.busy or not self.scan:
            return
        self.watchdog.stop()
        self.later.stop()
        ref = pick_service(self.found)
        if ref:
            self._stop_scan()
            self.session.nav.playService(eServiceReference(ref))
            return self._finish(ref, None)
        self._next()

    def _stop_scan(self):
        self.watchdog.stop()
        self.later.stop()
        for c in self._conns:
            _disconnect(c)
        self._conns = []
        self.scan = None

    def _finish(self, ref, error):
        self._stop_scan()
        self.busy = False
        self.done(ref, self.sr if ref else None, error)


def signal(session):
    """(SNR in dB or None, quality 0 to 100 or None, locked) for what is playing."""
    try:
        service = session.nav.getCurrentService()
        fe = service and service.frontendInfo()
        st = fe and fe.getFrontendStatus()
    except Exception:
        st = None
    if not st:
        return None, None, False
    db = st.get("tuner_signal_quality_db")
    db = db / 100.0 if isinstance(db, Integral) and 0 < db < 0x10000 else None
    q = st.get("tuner_signal_quality")
    q = q * 100 // 65535 if isinstance(q, Integral) and 0 <= q <= 65535 else None
    return db, q, bool(st.get("tuner_locked"))


def level(session):
    """The signal level in dBm, where the demodulator is one Lynx knows how
    to read it from (the RS6060), else None."""
    try:
        from . import rs6060
        if not rs6060.find_cached():
            return None
        st = session.nav.getCurrentService().frontendInfo().getFrontendStatus()
        p = st.get("tuner_signal_power")
        return rs6060.level_dbm(p) if isinstance(p, Integral) else None
    except Exception:
        return None


def signal_text(session, margin=None):
    db, q, locked = signal(session)
    if not locked:
        return _("No lock")
    if db is not None:
        if margin is not None:
            return _("SNR %.1f dB  margin %+.1f") % (db, margin)
        return _("SNR %.1f dB") % db
    return _("Signal %d%%") % q if q is not None else _("Locked")


# Fallbacks for when Tools.Transponder is missing: the enums Enigma2 uses.
FEC_NAMES = {1: "1/2", 2: "2/3", 3: "3/4", 4: "5/6", 5: "7/8", 6: "8/9",
             7: "3/5", 8: "4/5", 9: "9/10"}
SYSTEM_NAMES = {0: "DVB-S", 1: "DVB-S2"}
MODULATION_NAMES = {1: "QPSK", 2: "8PSK", 4: "16APSK", 5: "32APSK"}


def _named(human, raw, key, table):
    v = human.get(key)
    if v and str(v).lower() not in ("auto", "unknown", "none", "n/a"):
        return str(v)
    return table.get(raw.get(key))


_logged = []

# DVB emphasis on/off control codes some encoders put in service names.
# Python 2 sees the UTF-8 bytes; Python 3 sees the characters.
_EMPHASIS = (("\xc2\x86", "\xc2\x87") if sys.version_info[0] < 3 else ("\x86", "\x87"))


def clean_name(name):
    for c in _EMPHASIS:
        name = name.replace(c, "")
    return name.strip()


def live(session):
    """What the tuner and decoder report for what is playing, rather than
    what the list says: the broadcast name, sr_ks, system, modulation,
    fec, and the picture size as (width, height). Anything not reported
    is left out."""
    out = {}
    try:
        service = session.nav.getCurrentService()
    except Exception:
        return out
    if not service:
        return out
    try:
        fe = service.frontendInfo()
        raw = (fe and fe.getAll(False)) or {}    # False: as locked, not as asked
    except Exception:
        raw = {}
    try:
        from Tools.Transponder import ConvertToHumanReadable
        human = ConvertToHumanReadable(raw) if raw else {}
    except Exception:
        human = {}
    if raw and not _logged:
        # Once per run: everything the tuner reports, to see what this
        # driver gives (the H11S's reports FEC as auto).
        _logged.append(1)
        log("frontend data: %r" % (raw,))
        log("readable: %r" % (human,))
    sr = raw.get("symbol_rate")
    if isinstance(sr, Integral) and sr > 0:
        out["sr_ks"] = int(round(sr / 1000.0))
    # Lynx always asks for FEC auto. A driver that still says auto after
    # lock is echoing the request rather than reporting the demodulator
    # (the H11S's does, 20 Oct 2026), so its system and modulation are only
    # what Lynx asked for too: show none of them.
    if raw.get("fec_inner") not in FEC_NAMES:
        keys = ()
    else:
        keys = (("system", SYSTEM_NAMES), ("modulation", MODULATION_NAMES),
                ("fec_inner", FEC_NAMES))
    for key, table in keys:
        v = _named(human, raw, key, table)
        if v:
            out[key.replace("_inner", "")] = v
    if raw and not keys:
        # The driver only echoed the request: ask the demodulator itself.
        try:
            from . import rs6060
            out.update(rs6060.modcod())
        except Exception:
            pass
    try:
        info = service.info()
        name = info and info.getName()
        if name:
            # The name the repeater transmits (from its SDT), live.
            out["name"] = clean_name(name)
    except Exception:
        pass
    try:
        from enigma import iServiceInformation
        info = service.info()
        w = info.getInfo(iServiceInformation.sVideoWidth)
        h = info.getInfo(iServiceInformation.sVideoHeight)
        if 0 < w < 10000 and 0 < h < 10000:
            out["size"] = (w, h)
    except Exception:
        pass
    return out


def tech_text(freq_mhz, live_params, fallback_sr_ks=None):
    """The Lynx bar's second line, from live values only."""
    p = live_params
    parts = ["%g MHz" % freq_mhz]
    sr = p.get("sr_ks") or fallback_sr_ks
    if sr:
        parts.append("%d kS/s" % sr)
    mode = " ".join(x for x in (p.get("system"), p.get("modulation")) if x)
    if mode:
        parts.append(mode)
    if p.get("fec"):
        parts.append("FEC " + p["fec"])
    if p.get("pilots"):
        parts.append("pilots")
    if p.get("rolloff"):
        parts.append("roll-off " + p["rolloff"])
    if p.get("size"):
        parts.append("%dx%d" % p["size"])
    return "   ".join(parts)


def title_text(entry, live_params):
    """The Lynx bar's two top fields: (large, beside it). The broadcast name
    goes large when there is one; the list's callsign, town and distance
    go beside it, the callsign dropped if the broadcast name already says it."""
    km = "" if entry.get("km") is None else "   %s%d km" % ("~" if entry.get("approx") else "", round(entry["km"]))
    name = live_params.get("name") or ""
    if not name or name.upper() == entry["call"].upper():
        return entry["call"], entry["town"] + km
    if entry["call"].upper() in name.upper():
        return name, entry["town"] + km
    return name, "%s   %s%s" % (entry["call"], entry["town"], km)


def match_playing(entries, ref, name=""):
    """Which list entry a service reference is, for a channel Lynx did not
    start itself (after a restart the box carries on with the last one).
    A BATC stream is matched by its stream name; a repeater on air by the
    frequency in the service's namespace (position 192 << 16 | MHz).
    Several repeaters share a frequency (1304 MHz: GB3KM, GB3OO, GB3SQ), so
    the broadcast name decides when it holds a callsign; failing that the
    first in the list, which is the nearest when a locator is set.
    Returns the entry as Lynx would have it when watching, or None."""
    ref = ref or ""
    marker = "rtmp.batc.org.uk/live/"
    if marker in ref:
        key = ref.split(marker, 1)[1].split(":")[0].split(" ")[0].lower()
        for e in entries:
            s = e.get("stream")
            if s and s["key"].lower() == key:
                return dict(e, locked_sr_ks=None, via_stream=True)
        return None
    parts = ref.split(":")
    if len(parts) < 7 or parts[0] != "1":
        return None
    try:
        ns = int(parts[6], 16)
    except ValueError:
        return None
    if ns >> 16 != repeaters.BOX_ORBPOS:
        return None
    mhz = ns & 0xFFFF
    same = [e for e in entries if e.get("box_khz") and e["box_khz"] // 1000 == mhz]
    if not same:
        return None
    named = [e for e in same if e["call"].upper() in (name or "").upper()]
    e = (named or same)[0]
    return dict(e, locked_sr_ks=e["output"].get("sr_ks"))
