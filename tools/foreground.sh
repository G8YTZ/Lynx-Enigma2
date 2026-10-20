#!/bin/sh
# Run the box's GUI in this terminal, so Python errors show here, and save
# them to ~/lynx-run.log as well.
#   tools/foreground.sh [box address]
# Ctrl-C stops it and puts the normal GUI back.
BOX=${1:-192.168.0.164}
LOG="$HOME/lynx-run.log"
echo "Starting Enigma2 on $BOX in this terminal; log in $LOG. Ctrl-C to finish."
trap 'echo; echo "Putting the normal GUI back"; ssh root@"$BOX" "killall -9 enigma2 2>/dev/null; sleep 1; /sbin/init 3"; exit 0' INT
# -t gives the box a terminal, so Ctrl-C reaches enigma2 there and it stops
# instead of being left running in the background.
ssh -t root@"$BOX" "/sbin/init 4; sleep 2; killall -9 enigma2 2>/dev/null; sleep 1; enigma2" 2>&1 | tee "$LOG"
ssh root@"$BOX" "killall -9 enigma2 2>/dev/null; sleep 1; /sbin/init 3"
