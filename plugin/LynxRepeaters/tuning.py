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


def find_tuner(orbpos=repeaters.BOX_ORBPOS):
    """The first satellite tuner set up for the box's LNB position, else 0."""
    try:
        from Components.NimManager import nimmanager
        for slot in nimmanager.nim_slots:
            if not slot.isCompatible("DVB-S"):
                continue
            if any(sat[0] == orbpos for sat in nimmanager.getSatListForNim(slot.slot)):
                return slot.slot
    except Exception as e:            # an odd tuner set-up must not stop us
        print("[LynxRepeaters] tuner search: %s" % e)
    return 0


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
        self.busy = False

    def tune(self, entry, supply_v="13", hunt=False):
        self.entry, self.supply_v = entry, supply_v
        self.rates = symbol_rates(entry, hunt)
        self.tried = []
        self.feid = find_tuner()
        self.busy = True
        self.session.nav.stopService()      # free the tuner for the scan
        self._next()

    def cancel(self):
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
                print("[LynxRepeaters] found %s %s" % (ref, self.scan.getLastServiceName()))

    def _status(self):
        # Never tear the scan down from inside its own signal: do it next tick.
        if self.scan and self.scan.isDone():
            self.later.start(0, True)

    def _timeout(self):
        print("[LynxRepeaters] scan timed out at %d kS/s" % self.sr)
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
    db = db / 100.0 if isinstance(db, int) and 0 < db < 0x10000 else None
    q = st.get("tuner_signal_quality")
    q = q * 100 // 65535 if isinstance(q, int) and 0 <= q <= 65535 else None
    return db, q, bool(st.get("tuner_locked"))


def signal_text(session):
    db, q, locked = signal(session)
    if not locked:
        return _("No lock")
    if db is not None:
        return _("SNR %.1f dB") % db
    return _("Signal %d%%") % q if q is not None else _("Locked")
