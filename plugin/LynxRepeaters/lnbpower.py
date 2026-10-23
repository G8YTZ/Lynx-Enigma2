# Lynx-Enigma2: switch the LNB supply off.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Enigma2 has no setting for "no LNB power": its tuner set-up offers
polarisation, 13 V or 18 V. But the satellite equipment control underneath
does have one (eDVBSatelliteSwitchParameters._0V: the supply stays off when
a channel is tuned; openatv/enigma2 lib/dvb/sec.cpp, 23 Oct 2026). The
Python tuner set-up (Components.NimManager.SecConfigure.update) passes the
voltage mode for each satellite to it, so Lynx stands between the two:
while the supply is set to off, the voltage given for Lynx's position
(19.2E, which Lynx uses for every band) becomes _0V. Nothing is written to
the box's tuner settings, so switching back, or removing Lynx, puts things
as they were at the next GUI restart.

For a feed with no preamplifier, or a DC short across the antenna (Justin,
23 Oct 2026). It also cuts power to a real 19.2E dish on the same tuner.
"""
from __future__ import absolute_import, division, print_function

from .log import log
from .repeaters import BOX_ORBPOS

_state = {"off": False, "installed": False}


class _Sec(object):
    """The satellite equipment control, with setVoltageMode watched."""

    def __init__(self, sec, zero_v):
        self._sec, self._zero_v, self._sat = sec, zero_v, None

    def addLNB(self, *a):
        self._sat = None
        return self._sec.addLNB(*a)

    def addSatellite(self, orbpos, *a):
        self._sat = orbpos
        return self._sec.addSatellite(orbpos, *a)

    def setVoltageMode(self, mode, *a):
        if _state["off"] and self._sat == BOX_ORBPOS:
            mode = self._zero_v
        return self._sec.setVoltageMode(mode, *a)

    def __getattr__(self, name):
        return getattr(self._sec, name)


class _SecClass(object):
    """Stands in for eDVBSatelliteEquipmentControl inside NimManager."""

    def __init__(self, real, zero_v):
        self._real, self._zero_v = real, zero_v

    def getInstance(self):
        return _Sec(self._real.getInstance(), self._zero_v)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _install(nm):
    if _state["installed"] or isinstance(nm.secClass, _SecClass):
        _state["installed"] = True
        return True
    zero_v = getattr(nm.switchParam, "_0V", None)
    if zero_v is None:
        log("LNB power: this image has no 0 V mode")
        return False
    nm.secClass = _SecClass(nm.secClass, zero_v)
    _state["installed"] = True
    return True


def apply(off, nm=None):
    """Supply off (True) or back to normal (False) for Lynx's position, from
    the next tune. Returns False if this image cannot do it."""
    try:
        if nm is None:
            import Components.NimManager as nm
        if not off and not _state["installed"]:
            return True                    # never touched: nothing to undo
        if not _install(nm):
            return False
        if _state["off"] == bool(off):
            return True
        _state["off"] = bool(off)
        nm.nimmanager.sec.update()
        log("LNB power: %s" % ("off" if off else "on (13/18 V)"))
        return True
    except Exception as e:
        log("LNB power: %s" % e)
        return False
