#!/bin/sh
# MTRX RAIN: the engine, the BASIC program and the disk (out/MTRX-RAIN.D81), then the quick checks:
# the program in the BASIC 65 simulator, 10 s of rain and the 80-column check against the model.
# The longer runs (every key, the joysticks, a core without FCOLMCM, NTSC, the busiest frame):
#   python3 mega65/test_engine.py out
# The pictures and the video (a few minutes; ffmpeg):
#   python3 mega65/media.py out out/media
set -e
cd "$(dirname "$0")"
B=${B:-out}
python3 mega65/build.py $B
python3 mega65/test_launcher.py $B | tail -1
python3 mega65/test_engine.py $B glass mode | tail -1
sha256sum $B/MTRX-RAIN.D81
