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
import time

PPM4_DBFS = -18.0
DB_PER_DIVISION = 4.0
ATTACK_S = 0.0017
DECAY_S = 0.650
SILENCE = 1e-5
BLOCK_SAMPLES = 192                       # 4 ms at 48 kHz: still inside a PPM's 10 ms
                                          # integration, half the lines of 2 ms

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


# Where the decoded sound goes once metered: nowhere, but ffmpeg needs an
# output. OpenATV's ffmpeg is a cut-down build with no "null", "s16le",
# "wav" or "au" output (1 Nov 2026; it has ac3, adts, matroska, mpegts and a
# few more), so Lynx asks it what it has and uses the first of these
# (output format, audio encoder) pairs it can, writing to /dev/null.
DISCARD = (("null", None), ("s16le", "pcm_s16le"), ("wav", "pcm_s16le"), ("matroska", "pcm_s16le"),
           ("mpegts", "mp2"), ("adts", "aac"), ("ac3", "ac3"))


def muxers(text):
    """Output formats from ffmpeg -muxers (or -formats): lines such as
    "  E  mpegts   MPEG-TS", " DE  matroska ...", "  Ed alsa ..."."""
    out = set()
    for line in text.splitlines():
        m = re.match(r"\s*([D.\s]?E[d.\s]?)\s+([A-Za-z0-9_,]+)\s", line)
        if m and "E" in m.group(1):
            out.update(m.group(2).split(","))
    return out


def encoders(text):
    """Audio encoders from ffmpeg -encoders: lines such as " A....D aac  AAC"."""
    out = set()
    for line in text.splitlines():
        m = re.match(r"\s*A[A-Z.]{5}\s+(\S+)\s", line)
        if m:
            out.add(m.group(1))
    return out


def discard(available, codecs=None):
    """(output format, audio encoder or None) to throw the sound away with.
    Without an encoder list, PCM is taken as there (it nearly always is)."""
    for muxer, codec in DISCARD:
        if muxer not in available:
            continue
        if codec is None or (codec in codecs if codecs else codec.startswith("pcm_")):
            return muxer, codec
    return "matroska", "pcm_s16le"


# Reading the demux directly (2 Nov 2026). OpenATV's stream server on port
# 8001 writes in buffers of 188 x 1024 bytes: at a 1 MS/s repeater's 75 kB/s
# that is one lump every 2.5 s, so the meter lagged the sound by up to that
# and the needles froze between lumps, then raced (Justin: "on music the
# ballistics are all wrong"). Lynx now opens the playing service's demux
# itself, as Enigma2's own recorder does (demux.cpp eDVBTSRecorder), with
# only PAT, PMT and the sound, and hands ffmpeg the packets as they come.
DMX_START = 0x6f29                        # _IO('o', 41)
DMX_STOP = 0x6f2a                         # _IO('o', 42)
DMX_SET_PES_FILTER = 0x40146f2c           # _IOW('o', 44, struct dmx_pes_filter_params)
DMX_SET_BUFFER_SIZE = 0x6f2d              # _IO('o', 45)
DMX_ADD_PID = 0x40026f33                  # _IOW('o', 51, __u16)
DMX_IN_FRONTEND = 0
DMX_OUT_TSDEMUX_TAP = 3
DMX_PES_OTHER = 20
TAP_BUFFER = 64 * 1024                    # the demux's own buffer for our filter
TAP_READ = 188 * 16                       # read in small pieces: 3 kB, ~40 ms of AAC


def pes_filter(pid):
    """struct dmx_pes_filter_params: u16 pid, (pad), input, output, pes_type, flags."""
    import struct
    return struct.pack("=H2xIIII", pid, DMX_IN_FRONTEND, DMX_OUT_TSDEMUX_TAP, DMX_PES_OTHER, 0)


def tap_plan(data):
    """From Enigma2's getStreamingData() dict: (adapter, demux, [PAT, PMT,
    sound]) for the programme's sound, or None if there is no sound to meter."""
    if not data or "demux" not in data:
        return None
    pids = dict((kind, pid) for pid, kind in reversed(data.get("pids") or []))
    sounds = [pid for pid, kind in data.get("pids") or [] if kind == "audio"]
    sound = data.get("default_audio_pid", -1)
    if sound is None or sound < 0 or sound not in sounds:
        sound = sounds[0] if sounds else None
    if sound is None or "pmt" not in pids or data["demux"] < 0:
        return None
    return int(data.get("adapter", 0) or 0), int(data["demux"]), [0, pids["pmt"], sound]


def command(url, output=("null", None)):
    """ffmpeg, reading one programme's sound and printing per-block peaks.
    url "pipe:0" means transport stream on standard input (the demux tap)."""
    # No forcing to stereo: that mixed a mono programme into both channels
    # 3 dB down. Mono reads on channel 1 and the reader shows it on both
    # needles; 5.1 meters its front pair, which ffmpeg puts first.
    af = ("asetnsamples=n=%d:p=0,"
          "astats=metadata=1:reset=1:measure_perchannel=Peak_level:measure_overall=none,"
          "ametadata=mode=print:file=-:direct=1" % BLOCK_SAMPLES)   # direct: no output buffering
    # A short look at the stream before starting (the default can take
    # seconds), and no dynamic range control on AC-3, which would make
    # loud passages read low.
    return ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-analyzeduration", "700000", "-probesize", "400000", "-drc_scale", "0"
            ] + (["-f", "mpegts"] if url == "pipe:0" else []) + [
            "-i", url, "-vn", "-sn", "-dn", "-map", "0:a:0", "-af", af,
            "-metadata", "comment=" + MARKER] + (
        ["-f", "null", "-"] if output[0] == "null" else ["-c:a", output[1], "-f", output[0], "-y", "/dev/null"])


_PTS = re.compile(r"pts_time:\s*([-0-9.]+)")
_PEAK = re.compile(r"lavfi\.astats\.([12])\.Peak_level=(-?[0-9.]+|-inf|inf)")


class Reader(object):
    """Feeds ffmpeg's printed lines to two ballistics, left and right."""

    def __init__(self):
        self.meters = [Ballistics(), Ballistics()]
        self.last_pts = None
        self.dt = BLOCK_SAMPLES / 48000.0
        self.block = []                  # channels heard in the block being read
        self.first = None                # (wall clock, pts) when the first block arrived
        self.lag = 0.0                   # how far the meter has fallen behind, seconds

    def line(self, text):
        m = _PTS.search(text)
        if m:
            self._end_block()
            pts = float(m.group(1))
            now = time.time()
            if self.first is None:
                self.first = (now, pts)
            else:
                # Sound arriving slower than it plays means the meter is falling behind.
                self.lag = (now - self.first[0]) - (pts - self.first[1])
            if self.last_pts is not None and 0 < pts - self.last_pts < 0.1:
                self.dt = pts - self.last_pts
            self.last_pts = pts
            return
        m = _PEAK.search(text)
        if m:
            db = m.group(2)
            peak = 0.0 if db.endswith("inf") and db.startswith("-") else min(1.0, 10 ** (float(db) / 20))
            ch = int(m.group(1)) - 1
            self.meters[ch].update(peak, self.dt)
            self.block.append((ch, peak))

    def _end_block(self):
        """A mono programme has only channel 1: show it on both needles."""
        if len(self.block) == 1 and self.block[0][0] == 0:
            self.meters[1].update(self.block[0][1], self.dt)
        self.block = []

    def positions(self):
        return self.meters[0].position, self.meters[1].position

    def rest(self):
        for m in self.meters:
            m.level = SILENCE
        self.first, self.lag, self.last_pts = None, 0.0, None
