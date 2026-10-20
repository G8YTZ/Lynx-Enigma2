# Lynx-Enigma2: the magic eye.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""A tuning indicator in the style of a 6E5: a round green glow with a dark
shadow wedge that closes as the signal improves. It is driven by the margin:
the SNR above what the locked MODCOD needs to decode, which is what matters
when pointing an antenna (a plain level is fooled by noise or overload).

The pictures are drawn on a PC by tools/make_eye.py (smoothed, with
transparency) and the plugin flips between them. draw() below is the old
rectangle drawing, kept only as a fallback. No Enigma2 imports here.
"""
from __future__ import absolute_import, division, print_function

import math

# DVB-S2 Es/N0 (dB) for quasi-error-free reception, ideal AWGN (ETSI EN 302
# 307-1 table 13). A real receiver needs a little more, so a margin near 0
# is the edge.
S2_REQUIRED_DB = {
    ("QPSK", "1/4"): -2.35, ("QPSK", "1/3"): -1.24, ("QPSK", "2/5"): -0.30,
    ("QPSK", "1/2"): 1.00, ("QPSK", "3/5"): 2.23, ("QPSK", "2/3"): 3.10,
    ("QPSK", "3/4"): 4.03, ("QPSK", "4/5"): 4.68, ("QPSK", "5/6"): 5.18,
    ("QPSK", "8/9"): 6.20, ("QPSK", "9/10"): 6.42,
    ("8PSK", "3/5"): 5.50, ("8PSK", "2/3"): 6.62, ("8PSK", "3/4"): 7.91,
    ("8PSK", "5/6"): 9.35, ("8PSK", "8/9"): 10.69, ("8PSK", "9/10"): 11.03,
    ("16APSK", "2/3"): 8.97, ("16APSK", "3/4"): 10.21, ("16APSK", "4/5"): 11.03,
    ("16APSK", "5/6"): 11.61, ("16APSK", "8/9"): 12.89, ("16APSK", "9/10"): 13.13,
    ("32APSK", "3/4"): 12.73, ("32APSK", "4/5"): 13.64, ("32APSK", "5/6"): 14.28,
    ("32APSK", "8/9"): 15.69, ("32APSK", "9/10"): 16.05,
}

# Margin (dB) at which the eye is fully closed, and the shadow's half-angle
# (degrees) when wide open.
CLOSED_AT_DB = 10.0
OPEN_HALF_DEG = 55.0

GLOW = 0x5CFF7E          # the bright green of the target
RIM = 0x1E8A3C           # darker towards the edge
SHADOW = 0x0B2E14        # the shadow wedge
CAP = 0x262626           # the dark cap over the cathode
DARK = 0x0F1A12          # unlit: no signal, or a stream


def margin_db(snr_db, modulation=None, fec=None):
    """SNR above what the MODCOD needs, or None if the MODCOD is unknown."""
    need = S2_REQUIRED_DB.get((modulation, fec))
    if snr_db is None or need is None:
        return None
    return snr_db - need


# The level half: where the eye starts to close and where it is shut.
LEVEL_OPEN_DBM = -80.0
LEVEL_SHUT_DBM = -45.0
MARGIN_OPEN_DB = -3.0


def _part(value, lo, hi):
    return max(0.0, min(1.0, (value - lo) / float(hi - lo)))


def closure(locked, snr_db, margin, dbm=None):
    """0 (wide open) to 1 (closed). Half from the margin, which tells you
    about the edge of decoding but tops out once the transmitter's own
    quality limits the SNR (Lynx-Tx: about 19 dB, so +11 dB already at
    -30 dB on 21 Oct 2026); half from the level, which keeps rising with the
    signal but bottoms out near the edge. Without a level, the margin
    alone; without a MODCOD either, the SNR alone (closed at 20 dB)."""
    if not locked or snr_db is None:
        return 0.0
    if margin is None:
        m = _part(snr_db, 0.0, 20.0)
    else:
        m = _part(margin, MARGIN_OPEN_DB, CLOSED_AT_DB)
    if dbm is None:
        return m
    return 0.5 * m + 0.5 * _part(dbm, LEVEL_OPEN_DBM, LEVEL_SHUT_DBM)


FRAMES = 25   # eye/eye_00.png (open) to eye_24.png (closed), and eye_off.png


def frame(amount, lit):
    """Which picture to show: "off", or 0 to FRAMES - 1."""
    if not lit:
        return "off"
    return int(round(max(0.0, min(1.0, amount)) * (FRAMES - 1)))


def _cut(a, b, holes):
    """[a, b] minus the given intervals, as a list of intervals."""
    out = [(a, b)]
    for h0, h1 in holes:
        nxt = []
        for s0, s1 in out:
            if h1 <= s0 or h0 >= s1:
                nxt.append((s0, s1))
                continue
            if h0 > s0:
                nxt.append((s0, h0))
            if h1 < s1:
                nxt.append((h1, s1))
        out = nxt
    return out


def draw(size, amount, lit=True, step=2):
    """Rectangles (x, y, w, h, colour) for an eye `size` pixels across,
    `amount` closed (0 to 1)."""
    rects = []
    r = size / 2.0 - 1
    c = size / 2.0
    inner = r * 0.84
    cap = r * 0.30
    half = math.radians(OPEN_HALF_DEG * (1.0 - max(0.0, min(1.0, amount))))
    tan_half = math.tan(half)
    for y in range(0, size, step):
        dy = y + step / 2.0 - c
        if abs(dy) >= r:
            continue
        w_outer = math.sqrt(r * r - dy * dy)
        if not lit:
            rects.append((int(c - w_outer), y, int(2 * w_outer), step, DARK))
            continue
        # The shadow wedge opens upwards from the centre.
        holes = []
        if dy < 0 and half > 0:
            s = -dy * tan_half
            holes.append((c - s, c + s))
        if abs(dy) < cap:
            w_cap = math.sqrt(cap * cap - dy * dy)
            holes.append((c - w_cap, c + w_cap))
            rects.append((int(c - w_cap), y, max(1, int(2 * w_cap)), step, CAP))
        for a, b, colour in ((c - w_outer, c + w_outer, RIM),):
            for s0, s1 in _cut(a, b, holes):
                rects.append((int(s0), y, max(1, int(round(s1 - s0))), step, colour))
        if abs(dy) < inner:
            w_in = math.sqrt(inner * inner - dy * dy)
            for s0, s1 in _cut(c - w_in, c + w_in, holes):
                rects.append((int(s0), y, max(1, int(round(s1 - s0))), step, GLOW))
        for h0, h1 in holes[:1]:
            if dy < 0 and half > 0:
                lo, hi = max(h0, c - w_outer), min(h1, c + w_outer)
                if hi > lo:
                    rects.append((int(lo), y, max(1, int(round(hi - lo))), step, SHADOW))
    return rects
