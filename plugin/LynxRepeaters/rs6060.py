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
/sys/bus/i2c/devices/2-006b, name "rs6060") and its status register 0x7e
holds the DVB-S2 MODCOD, laid out as on its Montage cousin the M88DS3103
(the Linux m88ds3103 driver documents it):

  bits 0-3  code rate    bit 5  pilots    bits 6-7  modulation

Confirmed on the box, 21 Oct 2026: 0x76 with Lynx-Tx sending 8PSK 3/4,
pilots on; 0x75 after changing Lynx-Tx to 2/3. Not yet seen: QPSK (0 in
bits 6-7 by the M88DS3103's map) and pilots off.

Lynx only ever reads, one complete SMBus "read byte" transaction at a
time, which the kernel serialises with the driver's own traffic, so it
cannot upset the tuner. Anything unexpected and Lynx shows nothing.
DVB-S (different registers) is not decoded yet: not tested.
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

REG_S2_MODCOD = 0x7E

S2_FEC = {2: "2/5", 3: "1/2", 4: "3/5", 5: "2/3", 6: "3/4", 7: "4/5", 8: "5/6", 9: "8/9", 10: "9/10"}
S2_MODULATION = {0: "QPSK", 1: "8PSK", 2: "16APSK", 3: "32APSK"}


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


def decode_s2(value):
    """{"system", "modulation", "fec", "pilots"} from register 0x7e, or {} if
    the code rate is not a DVB-S2 one (not locked, or not DVB-S2)."""
    fec = S2_FEC.get(value & 0x0F)
    if not fec:
        return {}
    return {"system": "DVB-S2", "modulation": S2_MODULATION.get((value >> 6) & 0x03, "?"),
            "fec": fec, "pilots": bool(value & 0x20)}


_where = []


def modcod():
    """What the demodulator has locked to, or {} if there is no RS6060 or
    nothing sensible to read. Cheap enough to call once a second."""
    if not _where:
        _where.append(find())
    where = _where[0]
    if not where:
        return {}
    try:
        return decode_s2(read_byte(where[0], where[1], REG_S2_MODCOD))
    except (IOError, OSError, ValueError):
        return {}
