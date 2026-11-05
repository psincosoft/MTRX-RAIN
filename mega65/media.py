"""Pictures and a video of MTRX RAIN from the engine itself.

Every frame the engine leaves in its screen, colour RAM, character set and palette is drawn as the
VIC-IV draws 80 x 50 text (model.render's rule, with numpy here), two picture pixels to a MEGA65
pixel; every frame's registers of the four SIDs go through reSIDfp (pyresidfp, the 6581 model: not
the MEGA65's own SIDs), 50 frames a second, in stereo as the MEGA65's default mix has it (SIDs 1-2
right, 3-4 left: x0.74 to their own side, x0.25 to the other). The engine runs in test_engine.py's
model of the machine, with all of that run's checks.

One session, at the start's settings (speed 35 %, density 50 %, SOUND+HUMM):
  frame 900                 GREEN                         mtrx-rain-green.png
  P, then 3 s               AMBER                         mtrx-rain-gold.png
  P, then 3 s               ICE                           mtrx-rain-ice.png
  P, P                      RAINBOW, from green; the video from here, 42 s, with SPACE (time
                            stops) 24 s in and SPACE (time runs) 3.5 s later
  RAINBOW at red            the first frame its hue is red  mtrx-rain-red.png
Usage: python3 media.py BUILD OUTDIR [trial]   (trial: a few seconds of each, no red picture)
"""
import subprocess
import sys
import wave
from datetime import timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_engine as E  # noqa: E402
import model as M  # noqa: E402
import test_engine as T  # noqa: E402

RATE = 44100
SCALE = 2
TRIAL = len(sys.argv) > 3 and sys.argv[3] == 'trial'
GREEN_AT, STEP = (60, 20) if TRIAL else (900, 150)
RAINBOW_AT = GREEN_AT + 2 * STEP + 3          # the frame RAINBOW is chosen (P on PAPER)
VIDEO_FROM = RAINBOW_AT + 2
VIDEO_FRAMES = 150 if TRIAL else 42 * 50
STOP_AT, STOP_FOR = (VIDEO_FROM + 50, 40) if TRIAL else (VIDEO_FROM + 24 * 50, 175)
RED = range(166, 177)                         # RAINBOW's hues that are red (the wheel's 171)


def keys():
    return [(GREEN_AT + 2, T.P), (GREEN_AT + STEP + 2, T.P), (GREEN_AT + 2 * STEP + 2, T.P),
            (RAINBOW_AT, T.P), (STOP_AT, T.SPACE), (STOP_AT + STOP_FOR, T.SPACE)]


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


def save_png(img, path):
    from PIL import Image
    Image.fromarray(scaled(img)).save(path)


def synth(states):
    """Stereo samples (n x 2, float) for the frames' register states: SIDs 1-2 right, 3-4 left."""
    from pyresidfp import SoundInterfaceDevice
    from pyresidfp._pyresidfp import ChipModel
    from pyresidfp.registers import WritableRegister as W
    regs = list(W)
    chips = [SoundInterfaceDevice(model=ChipModel.MOS6581, clock_frequency=E.SID_CLOCK, sampling_frequency=RATE)
             for _ in range(4)]
    out = []
    for st in states:
        parts = []
        for k, chip in enumerate(chips):
            base = 0x20 * k
            for r in regs:
                chip.write_register(r, st[base + r.value])
            parts.append(np.array(chip.clock(timedelta(seconds=1 / 50)), dtype=np.float64))
        n = min(len(p) for p in parts)
        right = parts[0][:n] + parts[1][:n]
        left = parts[2][:n] + parts[3][:n]
        out.append(np.stack([0.74 * left + 0.25 * right, 0.74 * right + 0.25 * left], axis=1))
    return out


def main():
    bd, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    last = VIDEO_FROM + VIDEO_FRAMES
    mc = T.Machine(bd, limit=last + 2, keys=keys())
    sids, frames, shots, hues = {}, {}, {}, {}
    state = {'red': None}

    def on_frame(m, fr):
        sids[fr] = bytes(m.sid)
        hue, theme = m.var('HUE'), m.var('THEME')
        if fr % 50 == 0:
            hues[fr] = (theme, hue)
        want = {GREEN_AT: 'green', GREEN_AT + STEP: 'gold', GREEN_AT + 2 * STEP: 'ice'}.get(fr)
        if state['red'] is None and fr >= VIDEO_FROM and theme == M.T_RAINBOW and hue in RED:
            state['red'] = fr
            want = 'red'
        if want or VIDEO_FROM <= fr < last:
            scr, col, cs, rgb = m.picture()
            snap = (scr, col, rgb, bool(m.vic[0xD016] & 0x10), bool(m.vic[0xD063] & 0x40), m.vic[0xD021])
            if want:
                shots[want] = (fr, snap, cs, m.check_screen(fr))
            if VIDEO_FROM <= fr < last:
                frames[fr] = snap
                state['cs'] = cs

    code, steps = mc.call(limit_steps=150_000_000, on_frame=on_frame)
    ok = mc.after('media', M.EXIT_LIMIT)
    print(f"  {steps} instructions, {len(sids)} frames")
    for name in ('green', 'gold', 'ice') + (() if TRIAL else ('red',)):
        if name not in shots:
            sys.exit(f"no {name} picture (red: RAINBOW's hue never reached {RED.start}-{RED.stop - 1})")
        fr, (scr, col, rgb, mcm, fcol, bg), cs, probs = shots[name]
        if probs:
            print(f"  {name}: {probs}")
            ok = False
        bits = glyph_bits(cs)
        img = picture(scr, col, bits, rgb, mcm, fcol, bg)
        ref, _ = M.render(scr, col, cs, rgb, mcm, fcol, bg)
        if not np.array_equal(img, np.asarray(ref)):
            print(f"  {name}: the numpy picture differs from model.render's")
            ok = False
        save_png(img, out / f"mtrx-rain-{name}.png")
        print(f"  mtrx-rain-{name}.png: frame {fr}")
    print("  RAINBOW's hue each second:", ' '.join(f"{h}" for f, (t, h) in sorted(hues.items()) if t == M.T_RAINBOW))
    # the sound: every frame from the start (the envelopes as they were), the video's frames cut out;
    # a frame the engine did not reach in time keeps the registers of the one before
    seq, prev = [], bytes(0x80)
    for fr in range(last):
        prev = sids.get(fr, prev)
        seq.append(prev)
    pcm = synth(seq)
    clip = np.concatenate(pcm[VIDEO_FROM:last])
    peak = max(1.0, np.abs(clip).max())
    pcm16 = (clip / peak * 27000).astype(np.int16)
    wav = out / 'mtrx-rain-rainbow.wav'
    with wave.open(str(wav), 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm16.tobytes())
    # the picture: raw frames into ffmpeg
    bits = glyph_bits(state['cs'])
    mp4 = out / 'mtrx-rain-rainbow.mp4'
    h, w_ = 400 * SCALE, 640 * SCALE
    enc = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                            '-s', f'{w_}x{h}', '-framerate', '50', '-i', '-', '-i', str(wav),
                            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(mp4)],
                           stdin=subprocess.PIPE)
    for fr in range(VIDEO_FROM, last):
        scr, col, rgb, mcm, fcol, bg = frames[fr]
        enc.stdin.write(scaled(picture(scr, col, bits, rgb, mcm, fcol, bg)).tobytes())
    enc.stdin.close()
    if enc.wait():
        sys.exit('ffmpeg failed')
    print(f"  {mp4.name}: {VIDEO_FRAMES} frames ({VIDEO_FRAMES / 50:.0f} s), time stopped at {(STOP_AT - VIDEO_FROM) / 50:.0f} s "
          f"for {STOP_FOR / 50:.1f} s; the audio's peak {peak:.0f}")
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
