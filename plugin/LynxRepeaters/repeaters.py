# Lynx-Enigma2: the repeater list and how each output reaches the tuner.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""The repeater list (data/repeaters.json) and the arithmetic that turns a
repeater's output into something Enigma2's satellite tuner can tune.

A satellite tuner covers 950 to 2150 MHz. Each amateur band reaches it a
different way:

  23 cm  straight in, no LNB
  9 cm   a C-band LNB, oscillator 5150 MHz, above the signal (so the
         spectrum is inverted, which DVB-S2 sorts out by itself)
  3 cm   an LNB with a 9 GHz oscillator (a standard 9750 MHz one puts the
         10 GHz repeaters at 315 to 490 MHz, below the tuner)

Enigma2 then wants a "satellite" frequency. Out of the box (OpenATV, Zgemma
H11S, checked 20 Oct 2026) tuner A is set for a universal LNB: 9750 MHz
oscillator below 11700 MHz, no 22 kHz tone. So a signal arriving at the box
at IF MHz is tuned by asking for IF + 9750 MHz, whatever the band; nothing
in the box's tuner set-up has to change. Every IF here is below 1950 MHz,
which keeps it in the universal LNB's low band.

The polarisation chosen sets the LNB supply on the cable: vertical 13 V,
horizontal 18 V. That powers the small inline preamplifiers many people use,
and is harmless to a bare antenna on a DC-blocked feed.
"""
from __future__ import absolute_import, division, print_function

import io
import json
import math
import os
import sys

BOX_LO_MHZ = 9750          # the box's universal LNB, low band
TUNER_MIN, TUNER_MAX = 950, 2150

# Band: (low MHz, high MHz, default LNB oscillator MHz or 0 for none, what to fit)
BANDS = {
    "23cm": (1240, 1325, 0, "no LNB: straight into the box"),
    "9cm": (3300, 3500, 5150, "a C-band LNB (5150 MHz)"),
    "3cm": (10000, 10500, 9000, "an LNB with a 9 GHz oscillator"),
}

# The lowest symbol rate the Zgemma H11S's tuner locks to reliably (1000 kS/s
# usually works, 20 Oct 2026). Outputs below it are left off the list.
MIN_SR_KS = 1000

# Tried in turn when a repeater's symbol rate is not known.
COMMON_SR_KS = (2000, 1500, 1000, 4000, 1300, 3000)

# The satellite position tuner A's universal LNB is set up for (Astra 19.2E).
BOX_ORBPOS = 192

_HERE = os.path.dirname(os.path.abspath(__file__))
# On the box the list sits beside this file; in the repo it is in data/.
DATA_PATHS = (
    os.path.join(_HERE, "repeaters.json"),
    os.path.join(_HERE, "..", "..", "data", "repeaters.json"),
)
DATA = next((p for p in DATA_PATHS if os.path.exists(p)), DATA_PATHS[-1])


def band_of(freq_mhz):
    for name, (lo, hi, _osc, _what) in BANDS.items():
        if lo <= freq_mhz <= hi:
            return name
    return None


def if_mhz(freq_mhz, lnb_osc_mhz=0):
    """What arrives at the box: the signal itself, or what the LNB makes of it
    (|signal - oscillator|, an oscillator above the signal inverting it)."""
    return freq_mhz if not lnb_osc_mhz else abs(freq_mhz - lnb_osc_mhz)


def box_frequency_khz(freq_mhz, lnb_osc_mhz=0):
    """The frequency to give Enigma2, in kHz, for the box's universal LNB."""
    return int(round((if_mhz(freq_mhz, lnb_osc_mhz) + BOX_LO_MHZ) * 1000))


def tunable(freq_mhz, lnb_osc_mhz=0):
    return TUNER_MIN <= if_mhz(freq_mhz, lnb_osc_mhz) <= TUNER_MAX


def locator_to_latlon(loc):
    """Maidenhead locator (4 or 6 characters) to the middle of its square."""
    loc = (loc or "").strip().upper()
    if len(loc) < 4:
        return None
    try:
        lon = (ord(loc[0]) - 65) * 20 - 180 + int(loc[2]) * 2
        lat = (ord(loc[1]) - 65) * 10 - 90 + int(loc[3])
        if len(loc) >= 6:
            lon += (ord(loc[4]) - 65) * 5 / 60 + 2.5 / 60
            lat += (ord(loc[5]) - 65) * 2.5 / 60 + 1.25 / 60
        else:
            lon, lat = lon + 1, lat + 0.5
        return lat, lon
    except (ValueError, IndexError):
        return None


def distance_km(a, b):
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _native(x):
    """Python 2's json gives unicode; Enigma2's widgets there want str."""
    if isinstance(x, dict):
        return dict((_native(k), _native(v)) for k, v in x.items())
    if isinstance(x, list):
        return [_native(v) for v in x]
    if sys.version_info[0] < 3 and isinstance(x, unicode):  # noqa: F821
        return x.encode("utf-8")
    return x


def load(path=DATA):
    with io.open(path, encoding="utf-8") as f:
        return _native(json.load(f))["repeaters"]


def watchable(repeaters, lnb_osc=None):
    """Every digital output a box can tune, one entry per output, with the
    box frequency worked out. lnb_osc overrides the oscillator per band."""
    lnb_osc = lnb_osc or {}
    out = []
    for r in repeaters:
        for o in r.get("outputs", []):
            if o.get("mode") not in ("DVB-S", "DVB-S2", "digital", None):
                continue                      # analogue: the box cannot show it
            if o.get("sr_ks") and o["sr_ks"] < MIN_SR_KS:
                continue                      # below what the tuner locks to
            band = band_of(o["freq_mhz"])
            if not band:
                continue
            osc = lnb_osc.get(band, BANDS[band][2])
            if not tunable(o["freq_mhz"], osc):
                continue
            out.append(dict(r, output=o, band=band, lnb_osc_mhz=osc,
                            box_khz=box_frequency_khz(o["freq_mhz"], osc)))
    return out


def valid_locator(loc):
    """A 4 or 6 character Maidenhead locator, such as JO01 or JO01AJ."""
    loc = (loc or "").strip().upper()
    if len(loc) not in (4, 6):
        return False
    ok = "A" <= loc[0] <= "R" and "A" <= loc[1] <= "R" and loc[2:4].isdigit()
    return ok and (len(loc) == 4 or ("A" <= loc[4] <= "X" and "A" <= loc[5] <= "X"))


def position(r):
    """Where a repeater is, and whether that is only the middle of its
    locator square (no lat/lon in the list)."""
    if r.get("lat") is not None and r.get("lon") is not None:
        return (r["lat"], r["lon"]), False
    return locator_to_latlon(r.get("locator", "")), True


def note(entry):
    """The one-line warning for a list row, or an empty string."""
    status = entry.get("status", "on")
    if status == "off":
        return "Off air"
    if status != "on":
        return status[:1].upper() + status[1:]
    if entry["band"] != "23cm":
        return "Needs " + BANDS[entry["band"]][3]
    return ""


def rows(repeaters, home=None,
         lnb_osc=None, show_off=False):
    """The list as the plugin shows it: one entry per watchable output, with
    distance (km, or None without a home position), nearest first.
    show_off keeps repeaters ETCC lists as off air."""
    out = []
    for e in watchable(repeaters, lnb_osc):
        if not show_off and e.get("status") == "off":
            continue
        pos, approx = position(e)
        e["km"] = distance_km(home, pos) if home and pos else None
        e["approx"] = approx
        e["note"] = note(e)
        out.append(e)
    out.sort(key=lambda e: (e["km"] is None, e["km"] or 0, e["call"], e["output"]["freq_mhz"]))
    return out


# Tuning by hand, and the presets saved from it.

# The symbol rates offered when tuning by hand (Justin, 21 Oct 2026).
MANUAL_SR_KS = (1000, 1500, 2000, 3000, 4000)

# Kept beside the box's own settings, so a Lynx update leaves them alone.
PRESETS = "/etc/enigma2/lynx_presets.json"


def manual_entry(freq_mhz, sr_ks=None, name="", lnb_osc=None):
    """A frequency typed in, shaped like a list entry so the tuner and the
    Lynx bar treat it like any repeater. sr_ks None tries the common rates.
    A frequency outside the amateur bands is taken as going straight into
    the box. None if the box cannot tune it."""
    lnb_osc = lnb_osc or {}
    band = band_of(freq_mhz)
    osc = lnb_osc.get(band, BANDS[band][2]) if band else 0
    if not tunable(freq_mhz, osc):
        return None
    name = (name or "").strip()
    return {
        "call": name or "%g MHz" % freq_mhz,
        "town": "Preset" if name else "Tuned by hand",
        "locator": "", "keeper": None, "status": "on", "note": "",
        "km": None, "approx": False, "manual": True, "preset": bool(name),
        "output": {"freq_mhz": freq_mhz, "mode": None, "sr_ks": sr_ks, "fec": None,
                   "codec": None, "source": "by hand"},
        "band": band or "direct", "lnb_osc_mhz": osc,
        "box_khz": box_frequency_khz(freq_mhz, osc),
    }


def _preset(p):
    """A preset as saved, or None if it is not one."""
    try:
        name = str(p["name"]).strip()
        freq = float(p["freq_mhz"])
        sr = p.get("sr_ks")
        sr = int(sr) if sr else None
    except (KeyError, TypeError, ValueError):
        return None
    if not name or not TUNER_MIN <= freq <= 10500:
        return None
    return {"name": name, "freq_mhz": freq, "sr_ks": sr}


def load_presets(path=PRESETS):
    try:
        with io.open(path, encoding="utf-8") as f:
            raw = _native(json.load(f)).get("presets", [])
    except (IOError, OSError, ValueError, AttributeError):
        return []
    return [p for p in (_preset(x) for x in raw) if p]


def save_presets(presets, path=PRESETS):
    """Written whole and then renamed into place, so a power cut mid-write
    cannot leave half a file."""
    tmp = path + ".new"
    with open(tmp, "w") as f:
        json.dump({"presets": presets}, f, indent=1, sort_keys=True)
    os.rename(tmp, path)


def put_preset(presets, preset, replacing=None):
    """The list with this preset added, or put in place of the one called
    `replacing` (an edit) or of one with the same name. Kept in the order
    made, so the list does not jump about."""
    names = set(n.lower() for n in (preset["name"], replacing or "") if n)
    out, placed = [], False
    for p in presets:
        if p["name"].lower() in names:
            if not placed:
                out.append(preset)
                placed = True
        else:
            out.append(p)
    if not placed:
        out.append(preset)
    return out


def drop_preset(presets, name):
    return [p for p in presets if p["name"].lower() != name.lower()]
