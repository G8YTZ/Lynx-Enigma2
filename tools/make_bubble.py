#!/usr/bin/env python3
# Lynx-Enigma2: draw the chat bubbles (run on a PC, needs Pillow).
#
# Copyright (C) 2026 Justin Cockett, G8YTZ. GPL-2.0-or-later; see LICENSE.
"""iMessage-style blue speech bubbles for BATC chat on the picture (Justin,
2 Nov 2026), one per message height (1 to 5 lines of text), with a tail at
the bottom right. Drawn at four times the size and shrunk, so the edges are
smooth on any box (a skin's cornerRadius is not on older images and gave no
bubble at all on the first try).

  python3 tools/make_bubble.py

Sizes must match ChatBubbles in screens.py: 640 wide, padding 16, name line
38, text lines 36 each, tail 14 below, at 1920 x 1080; the hd/ set is two
thirds of that for 1280 x 720 menus.
"""
import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "plugin", "LynxRepeaters", "bubble")
SS = 4
W, PAD, WHO_H, LINE_H, TAIL, RADIUS = 640, 16, 38, 36, 12, 34
LINES = 5
BLUE = (10, 132, 255, 235)       # Apple's message blue, a touch see-through


def height(lines):
    return PAD + WHO_H + lines * LINE_H + PAD


def bubble(lines, scale):
    w, h = int(round(W * scale)), int(round((height(lines) + TAIL) * scale))
    body = int(round(height(lines) * scale))
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = RADIUS * scale * SS
    k = scale * SS                            # one Full HD pixel
    right = w * SS - 1 - 14 * k               # the body stops short of the tail's tip
    by = body * SS
    d.rounded_rectangle([0, 0, right, by - 1], radius=r, fill=BLUE)
    # The tail, as on a sent iMessage: from the body's right edge it sweeps
    # down to a tip below and to the right, and comes back curled in along
    # the bottom edge.
    def bez(p0, c, p1, n=24):
        return [((1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * c[0] + u * u * p1[0],
                 (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * c[1] + u * u * p1[1]) for u in [i / float(n) for i in range(n + 1)]]
    top = (right, by - 40 * k)
    tip = (right + 13 * k, by + TAIL * k - 1)
    foot = (right - 30 * k, by - 1)
    shape = bez(top, (right, by), tip) + bez(tip, (right - 6 * k, by + 4 * k), foot)
    d.polygon(shape + [(right - 30 * k, by - 40 * k)], fill=BLUE)
    return img.resize((w, h), Image.LANCZOS)


def main():
    for folder, scale in ((OUT, 1.0), (os.path.join(OUT, "hd"), 2.0 / 3)):
        os.makedirs(folder, exist_ok=True)
        for n in range(1, LINES + 1):
            bubble(n, scale).save(os.path.join(folder, "bubble_%d.png" % n), optimize=True)
    print("bubbles written to", OUT)


if __name__ == "__main__":
    main()
