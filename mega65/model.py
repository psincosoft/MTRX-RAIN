"""MTRX RAIN for the MEGA65: the specification the engine is generated from, and the picture it should show.

The rain in the MEGA65's terms:
- 80 x 50 text, 8 x 8 glyphs, mirrored. The bar on row 49 (K steps through the
  values, the keys and no bar; with no bar the rain takes all 50 rows).
- A cell's light is one byte of state: bits 7-6 its class (how fast it fades), bits 5-0 its age in
  ticks (1 = just lit); 0 = dark. Each tick every lit cell ages by one (NEXT) and shows the colour of
  its level (LEVEL, 1 to 111); a cell goes dark when its level would be under 3 %.
- Ticks: 25 a second at speed 100 %; speed 20 % to 250 % changes the tick rate, so strings fall and
  fade together. It starts at 35 %, density 50 %.
- Levels 0-127 map to palette entries ((L >> 3) << 4) | (L & 7): bit 3 always clear, so with MCM and
  FCOLMCM the VIC-IV paints each glyph in one colour, all 8 bits of the colour byte (viciv.vhdl:
  multicolour text, fullcolour_mcm). Level 0 is the background, 1-111 the trail (the theme's ramp,
  dark to bright), 112 the white head, 121-125 the bar (125 the white K of "K KEYS").
- Five palettes: GREEN, AMBER, ICE, PAPER, and RAINBOW, which goes round the colour wheel one step
  (1/256) for every new string, from green: each level is W + wheel x K / 256 a channel, W and K
  taken from GREEN, so that RAINBOW at its first step is GREEN in pure hues.
- A core without FCOLMCM (the bit reads back 0) gets the fallback: no MCM, colours 0-15, the trail in
  13 steps.
- Sound, S in turn: SOUND (the grains), HUMM (the drone), both, none; it starts with none.
Usage: python3 model.py [OUT_DIR]   (palette sheets, the rainbow's wheel, the bar's text)
"""
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import glyphs as G  # noqa: E402

VERSION = 2
SIGNATURE = b'MTR'
COLS, ROWS = 80, 50
BAR_ROW = 49
TICKS = 25                      # a second, at speed 100 %
CLASS_RATE = [1.45, 2.1, 3.0, 4.6]  # how fast each class of string fades, 1/s
VIS_MIN = 0.03                  # under this a cell is dark
LIT_MIN = 0.05                  # only cells at least this bright change their glyph
L_HEAD, L_TOP = 112, 111
L_BAR_DIM, L_BAR_VAL, L_BAR_FAINT, L_BAR_FG, L_BAR_KEY = 121, 122, 123, 124, 125
SPEEDS = [20, 35, 50, 70, 100, 130, 160, 200, 250]
SPEED0 = 1
DENSITIES = [20, 30, 40, 50, 60, 75, 90, 100]
DENS0 = 3
V_MIN, V_MAX = 8.0, 22.0        # rows a second at speed 100 %
P_HL, P_DEL, P_CHG, P_RNDCHG, P_VIS = 0.20, 0.07, 0.12, 0.08, 0.35
GAP_MIN, GAP_SPAN = 4, 14
CYCLES = 8                      # glyph changes a second at speed 100 % (times the root of the speed)
MAXD = 240                      # strings at once
EXIT_QUIT, EXIT_LIMIT, EXIT_MODE = 0x51, 0x4C, 0x57
SOUND_MODES = ['SOUND', 'HUMM', 'SOUND+HUMM', 'NO SOUND']
SOUND0 = 3                      # NO SOUND: the rain alone; S brings the sound in
DRONE_ON = [0, 1, 1, 0]
GRAIN_ON = [1, 0, 1, 0]

# glyph codes: the bar's letters 0-63; the rain's glyphs from 128 (static) and from 192 (changing)
G_STATIC, G_CHANGING = 128, 192


# ---------------------------------------------------------------- the cell states
def level_of(c, age):
    """The level (0-111) of a cell of class c, age ticks old (age 1 = just lit)."""
    b = math.exp(-(age - 1) * CLASS_RATE[c] / TICKS)
    if b < VIS_MIN:
        return 0
    return max(1, min(L_TOP, 1 + round(b * (L_TOP - 1))))


def max_age(c):
    a = 1
    while a < 63 and level_of(c, a + 1) > 0:
        a += 1
    return a


def state_tables():
    """NEXT[256]: the state a tick later; LEVEL[256]: the level a state shows. State 0 and age 0 are dark."""
    nxt, lev = [0] * 256, [0] * 256
    for c in range(4):
        m = max_age(c)
        assert level_of(c, m + 1) == 0 or m == 63, (c, m)
        for age in range(1, 64):
            s = (c << 6) | age
            if age <= m:
                lev[s] = level_of(c, age)
                nxt[s] = s + 1 if age < m else 0
    return nxt, lev


NEXT, LEVEL = state_tables()
LEVEL_LIT = min(L for L in range(1, 112) if (L - 1) / (L_TOP - 1) >= LIT_MIN)


def first_state(c):
    return (c << 6) | 1


# ---------------------------------------------------------------- the palettes
WHITE, BLACK = (255, 255, 255), (0, 0, 0)
THEMES = {
    'GREEN': dict(bg=(1, 6, 3), head=(236, 255, 240), key=WHITE,
                  stops=[(0, 1, 6, 3), (.12, 3, 36, 12), (.3, 7, 90, 27), (.55, 18, 163, 52), (.8, 47, 233, 92),
                         (1, 125, 255, 160)],
                  acc=(0x3d, 0xfc, 0x6a), dim=(0x19, 0xb3, 0x3e), faint=(0x0a, 0x4d, 0x1c), fg=(0xdc, 0xff, 0xe6)),
    'AMBER': dict(bg=(6, 3, 0), head=(255, 246, 224), key=WHITE,
                  stops=[(0, 6, 3, 0), (.12, 36, 18, 0), (.3, 90, 50, 0), (.55, 168, 98, 0), (.8, 240, 160, 0),
                         (1, 255, 210, 122)],
                  acc=(0xff, 0xb1, 0x00), dim=(0xc0, 0x7a, 0x00), faint=(0x57, 0x36, 0x08), fg=(0xff, 0xe9, 0xc2)),
    'ICE': dict(bg=(0, 4, 10), head=(239, 252, 255), key=WHITE,
                stops=[(0, 0, 4, 10), (.12, 0, 26, 38), (.3, 0, 74, 102), (.55, 10, 141, 184), (.8, 63, 210, 255),
                       (1, 168, 236, 255)],
                acc=(0x3f, 0xd2, 0xff), dim=(0x0a, 0x8d, 0xb8), faint=(0x00, 0x40, 0x5a), fg=(0xdf, 0xf7, 0xff)),
    'PAPER': dict(bg=(239, 233, 219), head=(0, 0, 0), key=BLACK,
                  stops=[(0, 239, 233, 219), (.12, 214, 207, 189), (.3, 176, 168, 147), (.55, 122, 115, 99),
                         (.8, 61, 56, 47), (1, 28, 26, 22)],
                  acc=(0x17, 0x15, 0x12), dim=(0x5c, 0x57, 0x4b), faint=(0xb9, 0xb3, 0xa1), fg=(0x1c, 0x1a, 0x16)),
}
RAINBOW = 'RAINBOW'
STATIC_THEMES = ['GREEN', 'AMBER', 'ICE', 'PAPER']
THEME_ORDER = STATIC_THEMES + [RAINBOW]
T_RAINBOW = THEME_ORDER.index(RAINBOW)


def tone(th, b):
    s = th['stops']
    if b >= 1:
        return s[-1][1:]
    for i in range(1, len(s)):
        if b <= s[i][0]:
            t = (b - s[i - 1][0]) / (s[i][0] - s[i - 1][0])
            return tuple(round(s[i - 1][j] + (s[i][j] - s[i - 1][j]) * t) for j in (1, 2, 3))
    return s[-1][1:]


def level_rgb(th, L):
    """The colour of level L (0-127) in a static theme th."""
    if L == 0:
        return th['bg']
    if L <= L_TOP:
        return tone(th, (L - 1) / (L_TOP - 1))
    if L == L_HEAD:
        return th['head']
    return {L_BAR_DIM: th['dim'], L_BAR_VAL: th['acc'], L_BAR_FAINT: th['faint'], L_BAR_FG: th['fg'],
            L_BAR_KEY: th['key']}.get(L, th['bg'])


def full_index(L):
    return ((L >> 3) << 4) | (L & 7)


# the fallback: 16 colours; 0 the background, 1-13 the trail, 14 the head (and the bar's K), 15 the bar
FB_TRAIL = 13


def fb_index(L):
    if L == 0:
        return 0
    if L <= L_TOP:
        return 1 + (L - 1) * FB_TRAIL // L_TOP
    if L in (L_HEAD, L_BAR_KEY):
        return 14
    return 15


def fb_level(k):
    """The level whose colour fallback entry k shows: two thirds up the trail levels it stands for."""
    if k == 0:
        return 0
    if k == 14:
        return L_HEAD
    if k == 15:
        return L_BAR_VAL
    ls = [L for L in range(1, L_TOP + 1) if fb_index(L) == k]
    return ls[len(ls) * 2 // 3]


FB_LEVEL = [fb_level(k) for k in range(16)]


def fb_rgb(th, k):
    return level_rgb(th, FB_LEVEL[k])


def swap(v):
    return ((v & 15) << 4) | (v >> 4)


def theme_planes(name):
    """128 levels as three planes (R, G, B), nybble-swapped, in level order: the engine writes level L
    to entry full_index(L)."""
    th = THEMES[name]
    return [bytes(swap(level_rgb(th, L)[k]) for L in range(128)) for k in range(3)]


def theme_planes_fb(name):
    th = THEMES[name]
    return [bytes(swap(fb_rgb(th, k)[j]) for k in range(16)) for j in range(3)]


CMAP_FULL = bytes(full_index(L) for L in range(128))
CMAP_FB = bytes(fb_index(L) for L in range(128))


# ---------------------------------------------------------------- RAINBOW
def wheel(h):
    """Hue h (0-255) at full saturation: green at 0, then cyan, blue, magenta, red, yellow."""
    a = (120 + h * 360 / 256) % 360
    x = 255 * (1 - abs((a / 60) % 2 - 1))
    r, g, b = [(255, x, 0), (x, 255, 0), (0, 255, x), (0, x, 255), (x, 0, 255), (255, 0, x)][int(a // 60)]
    return round(r), round(g), round(b)


WHEEL = [wheel(h) for h in range(256)]


def rb_wk(L):
    """Level L's white part W and hue weight K, from GREEN's colour of that level: W its red (its
    smallest channel), K what its green adds; W + K stays within 256 and K within 255."""
    if L == L_BAR_KEY:
        return 255, 0
    r, g, _ = level_rgb(THEMES['GREEN'], L)
    k = min(255, round((g - r) * 256 / 255), 256 - r)
    return r, k


RB_W = [rb_wk(L)[0] for L in range(128)]
RB_K = [rb_wk(L)[1] for L in range(128)]
RB_WF = [RB_W[FB_LEVEL[k]] for k in range(16)]
RB_KF = [RB_K[FB_LEVEL[k]] for k in range(16)]


def rainbow_rgb(L, hue):
    """Level L's colour at hue: W + wheel x K / 256 a channel, as the engine computes it (the
    multiplier's bits 8-15)."""
    return tuple(RB_W[L] + ((c * RB_K[L]) >> 8) for c in WHEEL[hue & 255])


def rainbow_planes(hue):
    return [bytes(swap(rainbow_rgb(L, hue)[k]) for L in range(128)) for k in range(3)]


def rainbow_planes_fb(hue):
    return [bytes(swap(rainbow_rgb(FB_LEVEL[e], hue)[k]) for e in range(16)) for k in range(3)]


for _L in range(128):
    assert RB_W[_L] + RB_K[_L] <= 256 and RB_K[_L] <= 255 and max(rainbow_rgb(_L, h)[0] for h in range(256)) <= 255


# ---------------------------------------------------------------- glyphs
def pool():
    """256 glyph numbers (0-52), each kind with its weight: kana 3, 日 2, digits 1.4,
    Z 1, marks 0.8."""
    w = []
    for g, (name, fl) in enumerate(zip(G.NAMES, G.FLAGS)):
        w.append(3 if 'k' in fl else 2 if name == 'nichi' else 1.4 if 'd' in fl else 1 if name == 'Z' else .8)
    tot = sum(w)
    share = [wt / tot * 256 for wt in w]
    n = [int(s) for s in share]
    for g in sorted(range(len(w)), key=lambda g: n[g] - share[g])[:256 - sum(n)]:
        n[g] += 1
    out = []
    for g in range(len(w)):
        out += [g] * n[g]
    # spread the kinds over the table, so that neighbouring entries differ
    out = [out[(i * 101) % 256] for i in range(256)]
    assert len(out) == 256 and sorted(set(out)) == list(range(G.N_GLYPHS))
    return bytes(out)


POOL = pool()


def charset():
    """The 2 KB character set the VIC-IV reads at $40000: the bar's letters at 0-63, the rain's glyphs
    (mirrored) at 128 and again at 192."""
    cs = bytearray(2048)
    for c, rows8 in enumerate(G.ui_font()):
        cs[c * 8:c * 8 + 8] = bytes(rows8)
    for base in (G_STATIC, G_CHANGING):
        for g, rows8 in enumerate(G.MIRRORED):
            cs[(base + g) * 8:(base + g) * 8 + 8] = bytes(rows8)
    return bytes(cs)


# ---------------------------------------------------------------- rates
def tick_rate(sp, fps):
    """Ticks a frame in 8.8."""
    return round(TICKS * sp / 100 / fps * 256)


def cycle_rate(sp, fps):
    return round(CYCLES * math.sqrt(sp / 100) / fps * 256)


def dens_threshold(d):
    """A free column starts a string with this chance in 256 a tick (1.6 times the density a second)."""
    return max(1, round(1.6 * d / 100 / TICKS * 256))


def speed_table():
    """256 string speeds in 8.8 rows a tick, V_MIN to V_MAX rows a second at speed 100 %."""
    return bytes(round((V_MIN + (V_MAX - V_MIN) * i / 255) / TICKS * 256) for i in range(256))


VTAB = speed_table()


# ---------------------------------------------------------------- the bar
def scr(text):
    """Text into the bar's screen codes (the upper-case set: @ A-Z 1-26, space 32, digits 48-57)."""
    out = []
    for ch in text:
        if 'A' <= ch <= 'Z':
            out.append(ord(ch) - 64)
        elif ch == '@':
            out.append(0)
        elif 32 <= ord(ch) < 64:
            out.append(ord(ch))
        else:
            raise ValueError(ch)
    return out


BAR_VALUES = "MTRX RAIN   SPEED ....   DENSITY ....   .......   .......   ..........   K KEYS"
BAR_KEYS = "<> SPEED  UP DOWN DENSITY  SPACE TIME  P PALETTE  S SOUND  K HIDE  Q QUIT"
FIELD_ORDER = ['speed', 'dens', 'theme', 'time', 'sound']
FIELD_VALUES = {
    'speed': [f"{s:3d}%" for s in SPEEDS],
    'dens': [f"{d:3d}%" for d in DENSITIES],
    'theme': [t.ljust(7) for t in THEME_ORDER],
    'time': ['RUNNING', 'STOPPED'],
    'sound': [s.ljust(10) for s in SOUND_MODES],
}


def _fields():
    """name: (column, width, values), the columns found as the template's runs of dots, in order."""
    runs, i = [], 0
    while i < len(BAR_VALUES):
        if BAR_VALUES[i] == '.':
            j = i
            while j < len(BAR_VALUES) and BAR_VALUES[j] == '.':
                j += 1
            runs.append((i, j - i))
            i = j
        else:
            i += 1
    assert len(runs) == len(FIELD_ORDER), runs
    return {n: (c, w, FIELD_VALUES[n]) for n, (c, w) in zip(FIELD_ORDER, runs)}


FIELDS = _fields()


def bar_template(page):
    """80 codes and 80 levels: page 0 the values (fields blank), 1 the keys."""
    text = (BAR_VALUES if page == 0 else BAR_KEYS).ljust(COLS)
    assert len(text) == COLS, len(text)
    codes = scr(text)
    lev = [L_BAR_DIM] * COLS
    if page == 0:
        for i in range(9):
            lev[i] = L_BAR_FG
        k = text.index('K KEYS')
        lev[k] = L_BAR_KEY
        for i in range(k + 2, k + 6):
            lev[i] = L_BAR_VAL
        for name, (col, w, vals) in FIELDS.items():
            for i in range(w):
                codes[col + i] = 32
                lev[col + i] = L_BAR_VAL
    else:
        # the keys bright, what they do dim
        pos = 0
        for wd in text.split('  '):
            if wd.strip():
                key = 'UP DOWN' if wd.startswith('UP DOWN') else wd.split(' ')[0]
                for i in range(len(key)):
                    lev[pos + i] = L_BAR_VAL
            pos += len(wd) + 2
    return codes, lev


def bar(page, state):
    """The bar as the engine should draw it: 80 codes and levels; state holds the field values."""
    codes, lev = bar_template(page)
    if page == 0:
        for name, (col, w, vals) in FIELDS.items():
            s = scr(vals[state[name]])
            assert len(s) == w, (name, vals)
            codes[col:col + w] = s
    return codes, lev


# check the fields sit where the template leaves room for them
for _n, (_c, _w, _v) in FIELDS.items():
    assert BAR_VALUES[_c:_c + _w] == '.' * _w, (_n, BAR_VALUES[_c:_c + _w])
    assert all(len(x) == _w for x in _v), _n


# ---------------------------------------------------------------- the picture
def render(screen, colram, cs, pal_rgb, mcm, fcolmcm, bg_index, png=None, scale=1):
    """What the VIC-IV shows in 80 x 50 text (viciv.vhdl, text mode, 8-bit characters): screen codes,
    colour bytes, the character set, the palette (256 RGB triples). With MCM: the colour byte's bit 3
    clear paints the glyph in one colour, all 8 bits with FCOLMCM, bits 0-2 without; bit 3 set would be
    multicolour (the engine never sets it, and it is counted). Without MCM: bits 0-3."""
    from PIL import Image
    img = Image.new('RGB', (COLS * 8, ROWS * 8))
    px = img.load()
    multi = 0
    bg = pal_rgb[bg_index]
    for r in range(ROWS):
        for c in range(COLS):
            k = r * COLS + c
            col = colram[k]
            if mcm:
                if col & 8:
                    multi += 1
                fg = pal_rgb[col] if fcolmcm else pal_rgb[col & 7]
            else:
                fg = pal_rgb[col & 15]
            g = cs[screen[k] * 8:screen[k] * 8 + 8]
            for y in range(8):
                bits = g[y]
                for x in range(8):
                    px[c * 8 + x, r * 8 + y] = fg if bits & (0x80 >> x) else bg
    if scale != 1:
        img = img.resize((COLS * 8 * scale, ROWS * 8 * scale), Image.NEAREST)
    if png:
        img.save(png)
    return img, multi


def sheet(path):
    """The static themes' 128 levels and the fallback's 16, as strips; then RAINBOW at 8 steps of the
    wheel."""
    from PIL import Image, ImageDraw
    rows = len(STATIC_THEMES) + 8
    img = Image.new('RGB', (128 * 6 + 20, rows * 50 + 20), (40, 40, 40))
    d = ImageDraw.Draw(img)
    for t, name in enumerate(STATIC_THEMES):
        th = THEMES[name]
        for L in range(128):
            d.rectangle([10 + L * 6, 10 + t * 50, 15 + L * 6, 34 + t * 50], fill=level_rgb(th, L))
        for k in range(16):
            d.rectangle([10 + k * 48, 36 + t * 50, 57 + k * 48, 44 + t * 50], fill=fb_rgb(th, k))
    for j in range(8):
        y = 10 + (len(STATIC_THEMES) + j) * 50
        hue = j * 32
        for L in range(128):
            d.rectangle([10 + L * 6, y, 15 + L * 6, y + 24], fill=rainbow_rgb(L, hue))
        for k in range(16):
            d.rectangle([10 + k * 48, y + 26, 57 + k * 48, y + 34], fill=rainbow_rgb(FB_LEVEL[k], hue))
    img.save(path)


def palette_rgb(theme, fallback=False, hue=0):
    """256 RGB triples as the engine leaves the palette (entries it does not write are black here)."""
    pal = [(0, 0, 0)] * 256
    if fallback:
        for k in range(16):
            pal[k] = rainbow_rgb(FB_LEVEL[k], hue) if theme == RAINBOW else fb_rgb(THEMES[theme], k)
    else:
        for L in range(128):
            pal[full_index(L)] = rainbow_rgb(L, hue) if theme == RAINBOW else level_rgb(THEMES[theme], L)
    return pal


if __name__ == '__main__':
    out = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / 'out')
    out.mkdir(parents=True, exist_ok=True)
    sheet(out / 'palettes.png')
    print('classes, max ages:', [max_age(c) for c in range(4)], 'lit from level', LEVEL_LIT)
    print('tick rates PAL', [tick_rate(s, 50) for s in SPEEDS], 'NTSC', [tick_rate(s, 60) for s in SPEEDS])
    print('cycle rates PAL', [cycle_rate(s, 50) for s in SPEEDS])
    print('density thresholds', [dens_threshold(d) for d in DENSITIES])
    print('rainbow W', RB_W[:12], '... K', RB_K[:12], '... head', RB_W[L_HEAD], RB_K[L_HEAD])
    for p in (0, 1):
        c, lv = bar(p, dict(speed=SPEED0, dens=DENS0, theme=0, time=0, sound=SOUND0))
        print(repr(''.join(chr(x + 64) if 1 <= x <= 26 else chr(x) if x >= 32 else '@' for x in c)))
