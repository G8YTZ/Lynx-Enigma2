#!/usr/bin/env python3
# Lynx-Enigma2: draw the PPM's pictures (run on a PC, needs Pillow).
#
# Copyright (C) 2026 Justin Cockett, G8YTZ. GPL-2.0-or-later; see LICENSE.
"""The BBC-style stereo PPM of Lynx Rx (lynx_overlay.py) and Lynx for Apple
TV (PPMView.swift), drawn to the same geometry as smooth pictures: the
housing with its scale, a red and a green needle at every whole degree of
the swing, and the zero-adjust screw that sits over both. The plugin stacks
them: housing, green needle, red needle (in front), screw.

  python3 tools/make_ppm.py
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "plugin"))
from LynxRepeaters.ppm import FRAMES, frame_angle   # noqa: E402

OUT = os.path.join(HERE, "..", "plugin", "LynxRepeaters", "ppm")
SS = 4                                   # drawn at four times the size, then shrunk
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HALF_SPAN = 40.0
MINOR_EXTRA = 6.0


class Geometry(object):
    """Lynx Rx draws in a 150 px box; everything scales from that."""

    def __init__(self, size):
        self.size = size
        self.px = size * SS
        self.s = self.px / 150.0
        self.centre = (75 * self.s, 75 * self.s)
        self.pivot = (self.centre[0], self.centre[1] + 25 * self.s)
        self.needle = 55 * self.s

    def point(self, r, degrees):
        t = math.radians(degrees)
        return (self.pivot[0] + r * math.sin(t), self.pivot[1] - r * math.cos(t))

    def blank(self):
        return Image.new("RGBA", (self.px, self.px), (0, 0, 0, 0))

    def done(self, img):
        return img.resize((self.size, self.size), Image.LANCZOS)


def line(d, a, b, colour, width):
    """A line with round ends, as the Apple TV draws it."""
    d.line([a, b], fill=colour, width=int(round(width)))
    r = width / 2.0
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=colour)


def scale_angle(ppm):
    return (ppm - 4) / 3.0 * HALF_SPAN


def housing(g):
    img = g.blank()
    d = ImageDraw.Draw(img)
    s, (cx, cy) = g.s, g.centre
    frame = 75 * s - SS
    d.ellipse([cx - frame, cy - frame, cx + frame, cy + frame], fill=(20, 20, 20, 230),
              outline=(128, 128, 128, 153), width=int(2 * s))
    inner = frame - 4 * s
    d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], outline=(77, 77, 77, 128), width=max(1, int(s)))
    small = ImageFont.truetype(FONT, int(14 * s))
    d.text((cx, cy + frame - 14 * s), "PPM", font=small, fill=(140, 140, 140, 255), anchor="mm")
    for a in (-HALF_SPAN - MINOR_EXTRA, HALF_SPAN + MINOR_EXTRA):
        line(d, g.point(g.needle - 3 * s, a), g.point(g.needle + 4 * s, a), (255, 255, 255, 255), 1.2 * s)
    numbers = ImageFont.truetype(FONT_BOLD, int(13 * s))
    for mark in range(1, 8):
        a = scale_angle(mark)
        line(d, g.point(g.needle - 9 * s, a), g.point(g.needle + 4 * s, a), (255, 255, 255, 255),
             (2.2 if mark == 4 else 1.4) * s)
        # Every number, at every size (Justin, 1 Nov 2026: 1, 4 and 7 alone would not do).
        d.text(g.point(g.needle + 14 * s, a), str(mark), font=numbers, fill=(255, 255, 255, 255), anchor="mm")
    return g.done(img)


def needle(g, degrees, colour):
    img = g.blank()
    line(ImageDraw.Draw(img), g.pivot, g.point(g.needle, degrees), colour, 2.5 * g.s)
    return g.done(img)


def screw(g):
    img = g.blank()
    d = ImageDraw.Draw(img)
    s, (px, py) = g.s, g.pivot
    r = 10 * s
    d.ellipse([px - r, py - r, px + r, py + r], fill=(13, 13, 13, 255), outline=(102, 102, 102, 204),
              width=max(1, int(s)))
    slot = math.radians(20)
    dx, dy = r * 0.8 * math.cos(slot), r * 0.8 * math.sin(slot)
    line(d, (px - dx, py - dy), (px + dx, py + dy), (140, 140, 140, 230), 1.6 * s)
    return g.done(img)


def main():
    for size, sub in ((110, ""), (73, "hd")):
        out = os.path.join(OUT, sub) if sub else OUT
        if not os.path.isdir(out):
            os.makedirs(out)
        g = Geometry(size)
        housing(g).save(os.path.join(out, "housing.png"), optimize=True)
        screw(g).save(os.path.join(out, "screw.png"), optimize=True)
        for n in range(FRAMES):
            a = frame_angle(n)
            needle(g, a, (0, 255, 0, 255)).save(os.path.join(out, "green_%02d.png" % n), optimize=True)
            needle(g, a, (255, 0, 0, 255)).save(os.path.join(out, "red_%02d.png" % n), optimize=True)
        print("PPM at %d px: housing, screw and %d needle positions each in %s" % (size, FRAMES, os.path.normpath(out)))


if __name__ == "__main__":
    main()
