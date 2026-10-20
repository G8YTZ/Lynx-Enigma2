#!/usr/bin/env python3
# Lynx-Enigma2: draw the magic eye's frames (run on a PC, needs Pillow).
#
# Copyright (C) 2026 Justin Cockett, G8YTZ. GPL-2.0-or-later; see LICENSE.
"""Draws the 6E5-style eye as PNG frames with transparency, smoothed by
drawing at four times the size and shrinking: eye_00.png (wide open) to
eye_24.png (closed), and eye_off.png (no signal). The plugin flips between
them, which looks far better than drawing on the box and costs it nothing.

  python3 tools/make_eye.py
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "plugin", "LynxRepeaters", "eye")
SIZE = 110            # pixels at 1920 x 1080; Enigma2 scales for other outputs
SS = 4                # drawn at four times the size, then shrunk
FRAMES = 25           # 0 .. 24
OPEN_HALF_DEG = 80.0  # the shadow's half-angle when wide open (160 degrees, as a 6E5)


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(len(a)))


def disc(size, glow_inner, glow_outer, cap_colour, lit):
    """The target: a radial glow, darker towards the rim, with the cap."""
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    px = img.load()
    c = s / 2.0
    r = s / 2.0 - 2 * SS
    for y in range(s):
        for x in range(s):
            d = math.hypot(x + 0.5 - c, y + 0.5 - c) / r
            if d <= 1.0:
                if lit:
                    # Brightest a third of the way out, as the glow sits on the
                    # target round the cap, falling off to the rim.
                    t = min(1.0, abs(d - 0.45) / 0.55)
                    px[x, y] = lerp(glow_inner, glow_outer, t ** 1.4) + (255,)
                else:
                    px[x, y] = (16, 28, 20, 255)
    # A thin dark ring at the rim, as the glass edge.
    ImageDraw.Draw(img).ellipse([c - r, c - r, c + r, c + r], outline=(8, 14, 10, 255), width=2 * SS)
    return img


def frame(amount, lit=True):
    s = SIZE * SS
    glow_in, glow_out = (150, 255, 160), (20, 120, 50)
    img = disc(SIZE, glow_in, glow_out, None, lit)
    c = s / 2.0
    r = s / 2.0 - 2 * SS
    if lit:
        half = math.radians(OPEN_HALF_DEG * (1.0 - amount))
        if half > 0.002:
            # The shadow wedge, upwards from the centre, with soft edges.
            wedge = Image.new("L", (s, s), 0)
            reach = r * 3.0           # well past the rim, so the edges meet the glass
            pts = [(c, c),
                   (c - reach * math.sin(half), c - reach * math.cos(half)),
                   (c + reach * math.sin(half), c - reach * math.cos(half))]
            ImageDraw.Draw(wedge).polygon(pts, fill=255)
            wedge = wedge.filter(ImageFilter.GaussianBlur(1.5 * SS))
            shadow = Image.new("RGBA", (s, s), (10, 40, 18, 255))
            mask = Image.new("L", (s, s), 0)
            ImageDraw.Draw(mask).ellipse([c - r, c - r, c + r, c + r], fill=255)
            img.paste(shadow, (0, 0), Image.composite(wedge, Image.new("L", (s, s), 0), mask))
    # The cap over the cathode: dark, with a faint sheen at the top.
    cap = r * 0.30
    d = ImageDraw.Draw(img)
    d.ellipse([c - cap, c - cap, c + cap, c + cap], fill=(34, 34, 34, 255))
    d.ellipse([c - cap * 0.6, c - cap * 0.85, c + cap * 0.6, c - cap * 0.1], fill=(58, 58, 58, 255))
    d.ellipse([c - cap, c - cap, c + cap, c + cap], outline=(18, 18, 18, 255), width=SS)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    # Full HD (110 px) and, for boxes with a 1280 x 720 skin, HD (73 px).
    global SIZE
    for size, sub in ((110, ""), (73, "hd")):
        SIZE = size
        out = os.path.join(OUT, sub) if sub else OUT
        if not os.path.isdir(out):
            os.makedirs(out)
        for n in range(FRAMES):
            frame(n / (FRAMES - 1.0)).save(os.path.join(out, "eye_%02d.png" % n), optimize=True)
        frame(0.0, lit=False).save(os.path.join(out, "eye_off.png"), optimize=True)
        print("%d frames and eye_off.png at %d px in %s" % (FRAMES, size, os.path.normpath(out)))


if __name__ == "__main__":
    main()
