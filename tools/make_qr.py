#!/usr/bin/env python3
# Lynx-Enigma2: draw the QR code for BATC's incident report form (run on a
# PC, needs qrcode and Pillow: pip install qrcode pillow).
#
# Copyright (C) 2026 Justin Cockett, G8YTZ. GPL-2.0-or-later; see LICENSE.
"""The box has no browser, so "report a chat message" shows this code to
scan with a phone (2 Nov 2026). White border, black squares: phones read
it best that way round even on a dark screen.

  python3 tools/make_qr.py
"""
import os

import qrcode

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "plugin", "LynxRepeaters", "qr")
URL = "https://batc.org.uk/incident-report-form/"
SIZE = 300                     # pixels at 1920 x 1080; hd/ is two thirds


def main():
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=4)
    q.add_data(URL)
    q.make(fit=True)
    img = q.make_image(fill_color="black", back_color="white").convert("RGB")
    for folder, size in ((OUT, SIZE), (os.path.join(OUT, "hd"), SIZE * 2 // 3)):
        os.makedirs(folder, exist_ok=True)
        # Whole pixels per square, so the edges stay sharp.
        n = img.size[0]
        scaled = img.resize((n * (size // n), n * (size // n)), 0)
        scaled.save(os.path.join(folder, "report.png"), optimize=True)
    print("QR code for", URL, "written to", OUT)


if __name__ == "__main__":
    main()
