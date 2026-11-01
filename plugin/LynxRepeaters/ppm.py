# Lynx-Enigma2: the PPM audio meter.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""Lynx Rx's BBC-style stereo PPM (lynx_overlay.py; PPMView.swift on Apple
TV), for the Enigma2 box (Justin, 1 Nov 2026).

The box decodes the sound in hardware, straight to HDMI, so Lynx never sees
it. But OpenATV serves whatever it is playing as a transport stream on port
8001 of the box itself, from the same tuner (checked 1 Nov 2026). ffmpeg
reads that, decodes the audio only, and prints each channel's peak for
every 2 ms block; Lynx runs the PPM ballistics on those peaks.

Ballistics as Lynx Rx: PPM 4 = -18 dBFS (EBU R68), 4 dB a division, attack
time constant 1.7 ms, decay 650 ms. Lynx Rx steps them per sample and warns
that a whole block's peak gives badly wrong attack timing; that is for
blocks of hundreds of samples. A 2 ms block is near the attack time and
peaks within it are what the attack would catch anyway.

No Enigma2 imports here, so it tests on any PC.
"""
from __future__ import absolute_import, division, print_function

import math
import re

PPM4_DBFS = -18.0
DB_PER_DIVISION = 4.0
ATTACK_S = 0.0017
DECAY_S = 0.650
SILENCE = 1e-5
BLOCK_SAMPLES = 96                        # 2 ms at 48 kHz

# Needle pictures: one per whole degree of swing, -43 to +43. The scale's
# 1 and 7 sit at -40 and +40; below 1 and above 7 the needle moves 3
# degrees a division, the little overshoot of Lynx Rx and Apple TV.
FRAMES = 87
FIRST_ANGLE = -43.0
HALF_SPAN = 40.0

# The PPM's own ffmpeg can be found and stopped by this, and no other.
MARKER = "lynx-ppm"


class Ballistics(object):
    def __init__(self):
        self.level = SILENCE

    def update(self, peak, dt):
        """One block's peak (linear, 0 to 1) lasting dt seconds."""
        target = max(peak, SILENCE)
        tau = ATTACK_S if target > self.level else DECAY_S
        self.level += (target - self.level) * (1 - math.exp(-dt / tau))

    @property
    def dbfs(self):
        return 20 * math.log10(self.level)

    @property
    def position(self):
        """4.0 sits on PPM 4."""
        return 4 + (self.dbfs - PPM4_DBFS) / DB_PER_DIVISION


def angle(position):
    """Needle angle in degrees for a meter position, overshoot included."""
    p = max(0.0, min(8.0, position))
    if p < 1:
        return -HALF_SPAN - (1 - p) * 3
    if p > 7:
        return HALF_SPAN + (p - 7) * 3
    return (p - 4) / 3.0 * HALF_SPAN


def frame(position):
    """Which needle picture shows this meter position."""
    n = int(round(angle(position) - FIRST_ANGLE))
    return max(0, min(FRAMES - 1, n))


def frame_angle(n):
    return FIRST_ANGLE + n


# Where the decoded sound goes once metered: nowhere. OpenATV's ffmpeg has
# no "null" output format (1 Nov 2026: "Requested output format 'null' is
# not known"), so raw PCM to /dev/null is the usual choice; the first of
# these that the box's ffmpeg has is used.
DISCARD = ("null", "s16le", "wav", "au")


def muxers(text):
    """The output formats ffmpeg -muxers lists, from its text."""
    out = set()
    for line in text.splitlines():
        m = re.match(r"\s*[D ]?E[ d]?\s+([A-Za-z0-9_,]+)\s", line)
        if m:
            out.update(m.group(1).split(","))
    return out


def discard(available):
    for name in DISCARD:
        if name in available:
            return name
    return "s16le"


def command(url, muxer="null"):
    """ffmpeg, reading one programme's sound and printing per-block peaks."""
    af = ("aformat=channel_layouts=stereo,asetnsamples=n=%d:p=0,"
          "astats=metadata=1:reset=1:measure_perchannel=Peak_level:measure_overall=none,"
          "ametadata=mode=print:file=-" % BLOCK_SAMPLES)
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer",
            "-i", url, "-vn", "-sn", "-dn", "-map", "0:a:0", "-af", af,
            "-metadata", "comment=" + MARKER] + (
        ["-f", "null", "-"] if muxer == "null" else ["-c:a", "pcm_s16le", "-f", muxer, "-y", "/dev/null"])


_PTS = re.compile(r"pts_time:\s*([-0-9.]+)")
_PEAK = re.compile(r"lavfi\.astats\.([12])\.Peak_level=(-?[0-9.]+|-inf|inf)")


class Reader(object):
    """Feeds ffmpeg's printed lines to two ballistics, left and right."""

    def __init__(self):
        self.meters = [Ballistics(), Ballistics()]
        self.last_pts = None
        self.dt = BLOCK_SAMPLES / 48000.0

    def line(self, text):
        m = _PTS.search(text)
        if m:
            pts = float(m.group(1))
            if self.last_pts is not None and 0 < pts - self.last_pts < 0.1:
                self.dt = pts - self.last_pts
            self.last_pts = pts
            return
        m = _PEAK.search(text)
        if m:
            db = m.group(2)
            peak = 0.0 if db.endswith("inf") and db.startswith("-") else min(1.0, 10 ** (float(db) / 20))
            self.meters[int(m.group(1)) - 1].update(peak, self.dt)

    def positions(self):
        return self.meters[0].position, self.meters[1].position

    def rest(self):
        for m in self.meters:
            m.level = SILENCE
