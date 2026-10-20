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
from __future__ import annotations

import json
import math
import os

BOX_LO_MHZ = 9750          # the box's universal LNB, low band
TUNER_MIN, TUNER_MAX = 950, 2150

# Band: (low MHz, high MHz, default LNB oscillator MHz or 0 for none, what to fit)
BANDS = {
    "23cm": (1240, 1325, 0, "no LNB: straight into the box"),
    "9cm": (3300, 3500, 5150, "a C-band LNB (5150 MHz)"),
    "3cm": (10000, 10500, 9000, "an LNB with a 9 GHz oscillator"),
}

# Tried in turn when a repeater's symbol rate is not known.
COMMON_SR_KS = (2000, 1500, 1000, 4000, 1300, 3000)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "repeaters.json")


def band_of(freq_mhz: float) -> str | None:
    for name, (lo, hi, _osc, _what) in BANDS.items():
        if lo <= freq_mhz <= hi:
            return name
    return None


def if_mhz(freq_mhz: float, lnb_osc_mhz: float = 0) -> float:
    """What arrives at the box: the signal itself, or what the LNB makes of it
    (|signal - oscillator|, an oscillator above the signal inverting it)."""
    return freq_mhz if not lnb_osc_mhz else abs(freq_mhz - lnb_osc_mhz)


def box_frequency_khz(freq_mhz: float, lnb_osc_mhz: float = 0) -> int:
    """The frequency to give Enigma2, in kHz, for the box's universal LNB."""
    return int(round((if_mhz(freq_mhz, lnb_osc_mhz) + BOX_LO_MHZ) * 1000))


def tunable(freq_mhz: float, lnb_osc_mhz: float = 0) -> bool:
    return TUNER_MIN <= if_mhz(freq_mhz, lnb_osc_mhz) <= TUNER_MAX


def locator_to_latlon(loc: str) -> tuple[float, float] | None:
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


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = [(math.radians(x), math.radians(y)) for x, y in (a, b)]
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def load(path: str = DATA) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["repeaters"]


def watchable(repeaters: list[dict], lnb_osc: dict | None = None) -> list[dict]:
    """Every digital output a box can tune, one entry per output, with the
    box frequency worked out. lnb_osc overrides the oscillator per band."""
    lnb_osc = lnb_osc or {}
    out = []
    for r in repeaters:
        for o in r.get("outputs", []):
            if o.get("mode") not in ("DVB-S", "DVB-S2", None):
                continue                      # analogue: the box cannot show it
            band = band_of(o["freq_mhz"])
            if not band:
                continue
            osc = lnb_osc.get(band, BANDS[band][2])
            if not tunable(o["freq_mhz"], osc):
                continue
            out.append(dict(r, output=o, band=band, lnb_osc_mhz=osc,
                            box_khz=box_frequency_khz(o["freq_mhz"], osc)))
    return out
