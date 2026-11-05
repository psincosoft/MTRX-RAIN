"""Pictures and a video of MTRX RAIN from the engine itself.

Every frame the engine leaves in its screen, colour RAM, character set and palette is drawn as the
VIC-IV draws 80 x 50 text (model.render's rule, with numpy here), two picture pixels to a MEGA65
pixel. The engine runs in test_engine.py's model of the machine, with all of that run's checks.

Two sessions, both from the start's settings (speed 35 %, density 50 %):
  pictures  frame 900 GREEN (mtrx-rain-green.png); P, 3 s on: AMBER (mtrx-rain-gold.png); P, 3 s
            on: ICE (mtrx-rain-ice.png); P, P: RAINBOW, from green; the first frame its hue is red:
            mtrx-rain-red.png; then Q
  video     K, K at once: the bottom row hidden, the rain on all 50 rows; GREEN for 18 s; then
            P four times in one frame: RAINBOW, from green; from there 42 s, mtrx-rain-rainbow.mp4,
            full screen and silent
Usage: python3 media.py BUILD OUTDIR [trial]   (trial: a few seconds of each, no red picture)
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import model as M  # noqa: E402
import test_engine as T  # noqa: E402

SCALE = 2
TRIAL = len(sys.argv) > 3 and sys.argv[3] == 'trial'
GREEN_AT, STEP = (60, 20) if TRIAL else (900, 150)
RAINBOW_AT = GREEN_AT + 2 * STEP + 3          # the frame RAINBOW is chosen (P on PAPER)
RED = range(166, 177)                         # RAINBOW's hues that are red (the wheel's 171)
VIDEO_FROM = 100 if TRIAL else 900
VIDEO_FRAMES = 150 if TRIAL else 42 * 50


def glyph_bits(cs):
    return np.unpackbits(np.frombuffer(cs, np.uint8).reshape(256, 8), axis=1).reshape(256, 8, 8).astype(bool)


def picture(scr, col, bits, pal_rgb, mcm, fcolmcm, bg_index):
    """The 640 x 400 picture (RGB, uint8) of one frame, by model.render's rule."""
    scr = np.frombuffer(scr, np.uint8).reshape(50, 80)
    col = np.frombuffer(col, np.uint8).reshape(50, 80)
    idx = (col if fcolmcm else col & 7) if mcm else col & 15
    pal = np.asarray(pal_rgb, np.uint8)
    fg = pal[idx]                                              # 50 x 80 x 3
    g = bits[scr]                                              # 50 x 80 x 8 x 8
    img = np.where(g[..., None], fg[:, :, None, None, :], pal[bg_index])
    return img.transpose(0, 2, 1, 3, 4).reshape(400, 640, 3)


def scaled(img):
    return np.repeat(np.repeat(img, SCALE, axis=0), SCALE, axis=1)


def snap(m):
    scr, col, cs, rgb = m.picture()
    return (scr, col, rgb, bool(m.vic[0xD016] & 0x10), bool(m.vic[0xD063] & 0x40), m.vic[0xD021]), cs


def pictures(bd, out):
    """GREEN, AMBER, ICE and RAINBOW at red, each checked cell by cell; True if all is well."""
    keys = [(GREEN_AT + 2, T.P), (GREEN_AT + STEP + 2, T.P), (GREEN_AT + 2 * STEP + 2, T.P), (RAINBOW_AT, T.P)]
    mc = T.Machine(bd, limit=6000, keys=keys)
    shots = {}

    def on_frame(m, fr):
        want = {GREEN_AT: 'green', GREEN_AT + STEP: 'gold', GREEN_AT + 2 * STEP: 'ice'}.get(fr)
        if 'red' not in shots and fr > RAINBOW_AT and m.var('THEME') == M.T_RAINBOW and m.var('HUE') in RED:
            want = 'red'
            m.keys.append((fr + 1, T.Q))
        if TRIAL and fr == GREEN_AT + 2 * STEP + 1:
            m.keys.append((fr + 1, T.Q))
        if want:
            s, cs = snap(m)
            shots[want] = (fr, s, cs, m.check_screen(fr))

    code, steps = mc.call(limit_steps=150_000_000, on_frame=on_frame)
    ok = mc.after('pictures', M.EXIT_QUIT)
    print(f"  {steps} instructions")
    for name in ('green', 'gold', 'ice') + (() if TRIAL else ('red',)):
        if name not in shots:
            sys.exit(f"no {name} picture")
        fr, (scr, col, rgb, mcm, fcol, bg), cs, probs = shots[name]
        if probs:
            print(f"  {name}: {probs}")
            ok = False
        img = picture(scr, col, glyph_bits(cs), rgb, mcm, fcol, bg)
        ref, _ = M.render(scr, col, cs, rgb, mcm, fcol, bg)
        if not np.array_equal(img, np.asarray(ref)):
            print(f"  {name}: the numpy picture differs from model.render's")
            ok = False
        from PIL import Image
        Image.fromarray(scaled(img)).save(out / f"mtrx-rain-{name}.png")
        print(f"  mtrx-rain-{name}.png: frame {fr}")
    return ok


def video(bd, out):
    """RAINBOW on the full screen, silent; True if all is well."""
    last = VIDEO_FROM + VIDEO_FRAMES
    keys = [(50, T.K), (52, T.K)] + [(VIDEO_FROM - 2, T.P)] * 4
    mc = T.Machine(bd, limit=last + 2, keys=keys)
    frames, hues, state = {}, {}, {}
    checks = [VIDEO_FROM, VIDEO_FROM + VIDEO_FRAMES // 2, last - 1]

    def on_frame(m, fr):
        if VIDEO_FROM <= fr < last:
            s, cs = snap(m)
            frames[fr] = s
            state['cs'] = cs
            if fr % 50 == 0:
                hues[fr] = m.var('HUE')
            if fr in checks:
                state[fr] = (m.check_screen(fr), m.var('BARPG'), m.var('NROWS'), m.var('THEME'))

    code, steps = mc.call(limit_steps=150_000_000, on_frame=on_frame)
    ok = mc.after('video', M.EXIT_LIMIT)
    print(f"  {steps} instructions")
    for fr in checks:
        probs, page, nrows, theme = state[fr]
        good = not probs and page == 2 and nrows == 50 and theme == M.T_RAINBOW
        print(f"  frame {fr}: {'full screen, RAINBOW, every cell as its state says' if good else (probs, page, nrows, theme)}")
        ok &= good
    print("  RAINBOW's hue each second:", ' '.join(str(h) for f, h in sorted(hues.items())))
    bits = glyph_bits(state['cs'])
    mp4 = out / 'mtrx-rain-rainbow.mp4'
    h, w = 400 * SCALE, 640 * SCALE
    enc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                            '-s', f'{w}x{h}', '-framerate', '50', '-i', '-', '-an',
                            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                            '-movflags', '+faststart', str(mp4)], stdin=subprocess.PIPE)
    for fr in range(VIDEO_FROM, last):
        scr, col, rgb, mcm, fcol, bg = frames[fr]
        enc.stdin.write(scaled(picture(scr, col, bits, rgb, mcm, fcol, bg)).tobytes())
    enc.stdin.close()
    if enc.wait():
        sys.exit('ffmpeg failed')
    print(f"  {mp4.name}: {VIDEO_FRAMES} frames ({VIDEO_FRAMES / 50:.0f} s), full screen, silent")
    return ok


def main():
    bd, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    ok = pictures(bd, out)
    ok &= video(bd, out)
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
