#!/bin/sh
# Copy the plugin and the repeater list to an Enigma2 box and restart its GUI.
#   tools/deploy.sh [box address] [--no-restart]
# Needs root SSH to the box (OpenATV: no password by default).
set -e
BOX=192.168.0.164
RESTART=1
for a in "$@"; do
    case "$a" in
        --no-restart) RESTART= ;;
        *) BOX="$a" ;;
    esac
done
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST=/usr/lib/enigma2/python/Plugins/Extensions/LynxRepeaters
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp "$HERE"/plugin/LynxRepeaters/*.py "$HERE/data/repeaters.json" "$STAGE/"
# COPYFILE_DISABLE stops macOS tar adding ._ files; tar over ssh avoids
# needing SFTP on the box; -m stops tar fussing when the box's clock is wrong.
COPYFILE_DISABLE=1 tar -C "$STAGE" -cf - . | \
    ssh root@"$BOX" "mkdir -p $DEST && rm -rf $DEST/__pycache__ && tar -m -C $DEST -xf -"
echo "Copied to $BOX:$DEST"
if [ -n "$RESTART" ]; then
    # /sbin is not on the box's PATH over SSH, hence the full paths.
    # Stop the GUI, clear any copies left by tools/foreground.sh, start it
    # again. Two copies at once fight over screen and tuner and hang the box.
    ssh root@"$BOX" "/sbin/init 4; sleep 2; killall -9 enigma2 2>/dev/null; sleep 1; /sbin/init 3"
    echo "GUI restarting; the plugin is under Plugins as UK ATV Repeaters."
fi
