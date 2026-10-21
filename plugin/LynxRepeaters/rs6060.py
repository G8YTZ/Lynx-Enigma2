# Lynx-Enigma2: read what a Montage RS6060 demodulator has really locked to.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version. See LICENSE.
"""The Zgemma H11S's tuner driver hands back what was asked for, not what
the demodulator found, so Enigma2 never learns the real modulation or FEC.
The demodulator itself knows. Linux lists it (on the H11S:
/sys/bus/i2c/devices/2-006b, name "rs6060"), and its registers are read the
way TBS's open driver reads them (tbsdtv/linux_media, m88rs6060.c,
m88rs6060_get_channel_info):

  0x08 bit 3     1 for DVB-S2, 0 for DVB-S
  0x19           DVB-S2 PLS code: MODCOD << 2, bit 1 short frames, bit 0 pilots
  0x76 bits 0-1  DVB-S2 roll-off: 0 0.35, 1 0.25, 2 0.20
  0xe6 bits 5-7  DVB-S code rate: 0 7/8, 1 5/6, 2 3/4, 3 2/3, 4 1/2

Checked on the box, 21 Oct 2026: 0x19 read 0x39 (MODCOD 14, 8PSK 3/4,
pilots) with Lynx-Tx on 8PSK 3/4 with pilots, and 0x76 read 0x30 (0.35).
(A first version read 0x7e in the M88DS3103 layout, which also reads
right: 8PSK 3/4 and 2/3, QPSK 3/4 and 16APSK 3/4 all checked. These are the
registers the maker's own driver uses, and they give roll-off and DVB-S.)

Lynx only ever reads, one complete SMBus "read byte" transaction at a
time, which the kernel serialises with the driver's own traffic, so it
cannot upset the tuner. Anything unexpected and Lynx shows nothing.
"""
from __future__ import absolute_import, division, print_function

import ctypes
import fcntl
import os

SYSFS = "/sys/bus/i2c/devices"
NAMES = ("rs6060",)

I2C_SLAVE_FORCE = 0x0706        # the kernel driver owns the chip: share it
I2C_SMBUS = 0x0720
I2C_SMBUS_READ = 1
I2C_SMBUS_BYTE_DATA = 2

REG_STATUS, REG_PLS, REG_ROLLOFF, REG_S_FEC = 0x08, 0x19, 0x76, 0xE6

# DVB-S2 MODCOD numbers (EN 302 307-1 table 12).
S2_MODCODS = {
    1: ("QPSK", "1/4"), 2: ("QPSK", "1/3"), 3: ("QPSK", "2/5"), 4: ("QPSK", "1/2"),
    5: ("QPSK", "3/5"), 6: ("QPSK", "2/3"), 7: ("QPSK", "3/4"), 8: ("QPSK", "4/5"),
    9: ("QPSK", "5/6"), 10: ("QPSK", "8/9"), 11: ("QPSK", "9/10"),
    12: ("8PSK", "3/5"), 13: ("8PSK", "2/3"), 14: ("8PSK", "3/4"), 15: ("8PSK", "5/6"),
    16: ("8PSK", "8/9"), 17: ("8PSK", "9/10"),
    18: ("16APSK", "2/3"), 19: ("16APSK", "3/4"), 20: ("16APSK", "4/5"), 21: ("16APSK", "5/6"),
    22: ("16APSK", "8/9"), 23: ("16APSK", "9/10"),
    24: ("32APSK", "3/4"), 25: ("32APSK", "4/5"), 26: ("32APSK", "5/6"), 27: ("32APSK", "8/9"),
    28: ("32APSK", "9/10"),
}
S2_ROLLOFF = {0: "0.35", 1: "0.25", 2: "0.20"}
S_FEC = {0: "7/8", 1: "5/6", 2: "3/4", 3: "2/3", 4: "1/2"}


class _Data(ctypes.Union):
    _fields_ = [("byte", ctypes.c_uint8), ("word", ctypes.c_uint16), ("block", ctypes.c_uint8 * 34)]


class _Args(ctypes.Structure):
    _fields_ = [("read_write", ctypes.c_uint8), ("command", ctypes.c_uint8),
                ("size", ctypes.c_uint32), ("data", ctypes.POINTER(_Data))]


def find(sysfs=SYSFS):
    """(bus, address) of the demodulator, from what Linux lists, or None."""
    try:
        entries = sorted(os.listdir(sysfs))
    except OSError:
        return None
    for e in entries:
        try:
            with open(os.path.join(sysfs, e, "name")) as f:
                name = f.read().strip()
        except (IOError, OSError):
            continue
        if name in NAMES and "-" in e:
            bus, addr = e.split("-", 1)
            try:
                return int(bus), int(addr, 16)
            except ValueError:
                continue
    return None


def read_byte(bus, addr, reg):
    fd = os.open("/dev/i2c-%d" % bus, os.O_RDWR)
    try:
        fcntl.ioctl(fd, I2C_SLAVE_FORCE, addr)
        data = _Data()
        args = _Args(I2C_SMBUS_READ, reg, I2C_SMBUS_BYTE_DATA, ctypes.pointer(data))
        fcntl.ioctl(fd, I2C_SMBUS, args)
        return data.byte
    finally:
        os.close(fd)


def decode_pls(pls, rolloff_reg=None):
    """What a DVB-S2 PLS code (register 0x19) means, or {} if it is not a
    plain DVB-S2 one (dummy frames, or DVB-S2X, not decoded yet)."""
    mc = S2_MODCODS.get((pls >> 2) & 0x3F) if pls < 0x80 else None
    if not mc:
        return {}
    out = {"system": "DVB-S2", "modulation": mc[0], "fec": mc[1], "pilots": bool(pls & 0x01),
           "short_frames": bool(pls & 0x02)}
    if rolloff_reg is not None and (rolloff_reg & 0x03) in S2_ROLLOFF:
        out["rolloff"] = S2_ROLLOFF[rolloff_reg & 0x03]
    return out


def decode_s(fec_reg):
    fec = S_FEC.get((fec_reg >> 5) & 0x07)
    return {"system": "DVB-S", "modulation": "QPSK", "fec": fec} if fec else {}


_where = []


def find_cached():
    if not _where:
        _where.append(find())
    return _where[0]


def modcod():
    """What the demodulator has locked to, or {} if there is no RS6060 or
    nothing sensible to read. Cheap enough to call once a second."""
    where = find_cached()
    if not where:
        return {}
    bus, addr = where
    try:
        if read_byte(bus, addr, REG_STATUS) & 0x08:
            return decode_pls(read_byte(bus, addr, REG_PLS), read_byte(bus, addr, REG_ROLLOFF))
        return decode_s(read_byte(bus, addr, REG_S_FEC))
    except (IOError, OSError, ValueError):
        return {}


def level_dbm(strength):
    """The signal level in dBm from the driver's 0 to 65535 strength, by
    running its sum backwards (TBS m88rs6060.c, m88rs6060_read_status):
    the tuner gain G (0.01 dB) maps to a percentage in three straight
    sections, x 656, and the level is -G / 100 + 2.79 dBm. None for 0 (no
    signal). Checked on the H11S, 21 Oct 2026: 32, 56, 72, 85 % for Lynx-Tx
    at -30, -20, -10, 0 dB gave -73, -65, -58, -49 dBm. Uncalibrated:
    good for comparing, within a few dB absolute."""
    if not strength:
        return None
    pct = strength / 656.0
    if pct < 5:
        return None
    if pct < 65:
        gain = 8500 - (pct - 5) * 100 / 3.0
    elif pct < 90:
        gain = 6500 - (pct - 65) * 200 / 3.0
    else:
        gain = 4500 - (pct - 90) * 500
    return -gain / 100.0 + 2.79
