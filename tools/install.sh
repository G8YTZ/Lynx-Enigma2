#!/bin/sh
# Lynx-Enigma2: install or update Lynx, run on the box itself.
#
#   opkg update && opkg upgrade
#   wget -qO- https://raw.githubusercontent.com/G8YTZ/Lynx-Enigma2/main/tools/install.sh | sh
#
# (the first line brings the box's own software up to date first)
#
# Installs the stream players (ServiceApp, gstplayer, exteplayer3) from the
# box's feed, downloads the latest Lynx from GitHub, puts the plugin and the
# repeater list in place, and restarts the GUI. Settings are kept: they live in the
# box's own settings file. Run it again at any time to update.
#
# Copyright (C) 2026 Justin Cockett, G8YTZ. GPL-2.0-or-later; see LICENSE.
set -e

# A box with no battery-backed clock starts at its image's build date (2021 on
# the Zgemma H11S). HTTPS then fails (certificates "not yet valid"), and so did
# the stream players' install on a new box (13 Nov 2026). Set it first.
if [ "$(date +%Y)" -lt 2025 ]; then
    for n in /usr/sbin/ntpdate /usr/bin/ntpdate /sbin/ntpdate; do
        if [ -x "$n" ]; then
            echo "Lynx: the box's clock says $(date +%Y); setting it"
            "$n" -b pool.ntp.org >/dev/null 2>&1 || true
            break
        fi
    done
fi

# The commit main is at, so the download matches it and Lynx can tell
# later whether there is a newer one (its start-up update check).
SHA=""
if [ -z "$LYNX_TARBALL" ]; then
    SHA=$(wget -qO- https://api.github.com/repos/G8YTZ/Lynx-Enigma2/commits/main 2>/dev/null \
          | grep -m1 '"sha"' | sed 's/.*"sha": *"\([0-9a-f]\{40\}\)".*/\1/')
    case "$SHA" in
        [0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
        *) SHA="" ;;
    esac
fi
if [ -n "$SHA" ]; then
    URL=https://github.com/G8YTZ/Lynx-Enigma2/archive/$SHA.tar.gz
else
    URL=${LYNX_TARBALL:-https://github.com/G8YTZ/Lynx-Enigma2/archive/refs/heads/main.tar.gz}
fi
DEST=${LYNX_DEST:-/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters}
WORK=/tmp/lynx-install.$$

# The stream players Lynx uses for BATC streams, from the box's own feed.
# Already there: opkg leaves them alone. Not available: Lynx still works,
# with the box's own player for streams.
if [ -z "$LYNX_NO_PLAYERS" ] && command -v opkg >/dev/null 2>&1; then
    echo "Lynx: making sure the stream players are installed"
    opkg update >/dev/null 2>&1 || true
    # The DVB media sink hands gstplayer's picture and sound to the box's
    # decoder: without it a stream plays with no picture (a new box, 13 Nov 2026).
    opkg install enigma2-plugin-systemplugins-serviceapp gstplayer exteplayer3 \
        gstreamer1.0-plugin-dvbmediasink >/dev/null 2>&1 || true
fi
PLAYERS_OK=1
if [ -z "$LYNX_NO_PLAYERS" ] && command -v opkg >/dev/null 2>&1; then
    for p in enigma2-plugin-systemplugins-serviceapp gstplayer exteplayer3; do
        opkg list-installed 2>/dev/null | grep -q "^$p " || PLAYERS_OK=""
    done
    if command -v gst-inspect-1.0 >/dev/null 2>&1; then
        gst-inspect-1.0 dvbvideosink >/dev/null 2>&1 || PLAYERS_OK=""
    fi
fi

echo "Lynx: downloading"
rm -rf "$WORK"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT
case "$URL" in
    http*) wget -q -O "$WORK/lynx.tar.gz" "$URL" ;;
    *) cp "$URL" "$WORK/lynx.tar.gz" ;;            # a local file, for testing
esac
tar -xzf "$WORK/lynx.tar.gz" -C "$WORK"
SRC=$(ls -d "$WORK"/*/plugin/LynxRepeaters 2>/dev/null | head -1)
if [ -z "$SRC" ] || [ ! -f "$SRC/plugin.py" ]; then
    echo "Lynx: the download did not contain the plugin; nothing changed." >&2
    exit 1
fi
TOP=${SRC%/plugin/LynxRepeaters}

echo "Lynx: installing to $DEST"
mkdir -p "$DEST"
rm -rf "$DEST/__pycache__"
rm -f "$DEST"/*.pyc "$DEST"/*.pyo
cp "$SRC"/*.py "$DEST/"
rm -rf "$DEST/eye"
cp -R "$SRC/eye" "$DEST/"
rm -rf "$DEST/ppm"
cp -R "$SRC/ppm" "$DEST/"
rm -rf "$DEST/bubble"
cp -R "$SRC/bubble" "$DEST/"
rm -rf "$DEST/qr"
cp -R "$SRC/qr" "$DEST/"
cp "$TOP/data/repeaters.json" "$DEST/"
if [ -n "$SHA" ]; then
    echo "$SHA" > "$DEST/version.txt"
else
    rm -f "$DEST/version.txt"
fi

if [ -z "$PLAYERS_OK" ]; then
    echo ""
    echo "************************************************************"
    echo "  Lynx is installed, but the stream players did not install."
    echo "  BATC streams may play with no picture. To fix, run:"
    echo ""
    echo "    opkg update"
    echo "    opkg install enigma2-plugin-systemplugins-serviceapp \\"
    echo "        gstplayer exteplayer3 gstreamer1.0-plugin-dvbmediasink"
    echo ""
    echo "  then run this installer again."
    echo "************************************************************"
    echo ""
fi

if [ -n "$LYNX_NO_RESTART" ]; then
    echo "Lynx: installed (GUI not restarted)"
    exit 0
fi
echo "Lynx: installed; restarting the GUI"
/sbin/init 4
sleep 2
killall -9 enigma2 2>/dev/null || true
sleep 1
/sbin/init 3
