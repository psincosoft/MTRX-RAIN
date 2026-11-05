"""MTRX RAIN for the MEGA65: the rain's glyphs, drawn by hand for the 8 x 8 character cell.

Thirty half-width katakana, the kanji 日, Z, the digits and a few marks, drawn pixel by pixel in a
7 x 7 box (columns 0-6, rows 0-6); column 7 and row 7 stay empty, the gap between neighbours.
READABLE is each glyph the right way round; MIRRORED is how the rain shows them: the kana and the
digits 2, 5 and 9 mirrored left to right, the digits 3 and 6 turned top to bottom.

The bottom bar's letters, digits and marks are the repository's own Commodore-style set
(tools/c64font.py), screen codes 0-63 of the upper-case set.
Usage: python3 glyphs.py [PREVIEW.png]   (a sheet of both sets, 8 x scale)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in (HERE.parent / 'tools', HERE.parent.parent / 'tools')
                            if (p / 'c64font.py').exists())))
import c64font  # noqa: E402

# name, flags (k kana, m mirror, v flip, d digit), 7 rows of 7 columns
SRC = [
    ('ha', 'km', """
..#....
..#.#..
.#...#.
.#...#.
#.....#
#.....#
......."""),
    ('hi', 'km', """
#......
#....#.
#.##...
##.....
#......
#......
.#####."""),
    ('shi', 'km', """
##.....
......#
##...#.
....#..
...#...
.##....
......."""),
    ('tsu', 'km', """
#..#..#
.#..#.#
......#
.....#.
....#..
..##...
......."""),
    ('u', 'km', """
...#...
#######
#.....#
#.....#
.....#.
....#..
..##..."""),
    ('cho', 'k', """
.......
.......
.......
#######
.......
.......
......."""),
    ('na', 'km', """
...#...
#######
...#...
...#...
..#....
.#.....
#......"""),
    ('mi', 'km', """
.###...
....##.
.###...
....##.
.......
####...
....###"""),
    ('mo', 'km', """
.#####.
..#....
#######
..#....
..#....
..#....
...####"""),
    ('ni', 'km', """
.......
.#####.
.......
.......
.......
#######
......."""),
    ('sa', 'km', """
.#...#.
#######
.#...#.
.#...#.
.....#.
....#..
..##..."""),
    ('wa', 'km', """
#######
#.....#
#.....#
.....#.
....#..
...#...
.##...."""),
    ('o', 'km', """
....#..
#######
...##..
..#.#..
.#..#..
#...#..
...##.."""),
    ('ri', 'km', """
#....#.
#....#.
#....#.
#....#.
.....#.
....#..
..##..."""),
    ('ho', 'km', """
...#...
#######
...#...
.#.#.#.
#..#..#
...#...
..##..."""),
    ('ma', 'km', """
#######
.....##
....##.
.#.##..
..##...
...#...
....#.."""),
    ('e', 'km', """
.#####.
...#...
...#...
...#...
...#...
#######
......."""),
    ('ki', 'km', """
..#....
.######
...#...
#######
...#...
....#..
....#.."""),
    ('mu', 'km', """
...#...
..#....
..#....
.#...#.
.#....#
#######
......."""),
    ('te', 'km', """
.#####.
.......
#######
...#...
...#...
..#....
##....."""),
    ('ke', 'km', """
.#.....
#######
#...#..
....#..
...#...
..#....
##....."""),
    ('me', 'km', """
.....#.
.#...#.
..#.#..
...#...
..#.#..
.#.....
#......"""),
    ('ka', 'km', """
..#....
#######
..#...#
.#....#
.#....#
#...#.#
.....#."""),
    ('yu', 'km', """
.......
#####..
....#..
....#..
....#..
#######
......."""),
    ('ra', 'km', """
.#####.
.......
#######
......#
.....#.
....#..
.##...."""),
    ('se', 'km', """
..#....
..#....
#######
..#..#.
..#.#..
..#....
...####"""),
    ('ne', 'km', """
...#...
.#####.
....#..
...#...
.###.#.
#..#..#
...#..."""),
    ('su', 'km', """
#######
.....#.
....#..
...#...
..#.#..
.#...#.
#.....#"""),
    ('ta', 'km', """
..#....
.#####.
#....#.
.##.#..
...#...
..#....
##....."""),
    ('nu', 'km', """
#######
.....#.
.#..#..
..##...
..##...
.#..#..
#......"""),
    ('nichi', '', """
.#####.
.#...#.
.#...#.
.#####.
.#...#.
.#...#.
.#####."""),
    ('Z', '', """
#######
.....#.
....#..
...#...
..#....
.#.....
#######"""),
    ('0', 'd', """
..###..
.#...#.
.#...#.
.#...#.
.#...#.
.#...#.
..###.."""),
    ('1', 'd', """
...#...
..##...
...#...
...#...
...#...
...#...
..###.."""),
    ('2', 'dm', """
..###..
.#...#.
.....#.
....#..
...#...
..#....
.#####."""),
    ('3', 'dv', """
.#####.
....#..
...#...
....#..
.....#.
.#...#.
..###.."""),
    ('4', 'd', """
....#..
...##..
..#.#..
.#..#..
.#####.
....#..
....#.."""),
    ('5', 'dm', """
.#####.
.#.....
.####..
.....#.
.....#.
.#...#.
..###.."""),
    ('6', 'dv', """
...##..
..#....
.#.....
.####..
.#...#.
.#...#.
..###.."""),
    ('7', 'd', """
.#####.
.....#.
....#..
...#...
..#....
..#....
..#...."""),
    ('8', 'd', """
..###..
.#...#.
.#...#.
..###..
.#...#.
.#...#.
..###.."""),
    ('9', 'dm', """
..###..
.#...#.
.#...#.
..####.
.....#.
....#..
..##..."""),
    ('star', '', """
.......
...#...
.#.#.#.
..###..
.#.#.#.
...#...
......."""),
    ('plus', '', """
.......
...#...
...#...
.#####.
...#...
...#...
......."""),
    ('colon', '', """
.......
...#...
.......
.......
.......
...#...
......."""),
    ('equals', '', """
.......
.......
.#####.
.......
.#####.
.......
......."""),
    ('dot', '', """
.......
.......
.......
.......
.......
...#...
......."""),
    ('less', '', """
....#..
...#...
..#....
.#.....
..#....
...#...
....#.."""),
    ('greater', '', """
..#....
...#...
....#..
.....#.
....#..
...#...
..#...."""),
    ('quote', '', """
..#.#..
..#.#..
.......
.......
.......
.......
......."""),
    ('bar', '', """
...#...
...#...
...#...
...#...
...#...
...#...
...#..."""),
    ('brokenbar', '', """
...#...
...#...
...#...
.......
...#...
...#...
...#..."""),
    ('underscore', '', """
.......
.......
.......
.......
.......
.......
#######"""),
]


def rows(art):
    r = [line for line in art.strip('\n').split('\n')]
    assert len(r) == 7 and all(len(x) == 7 and set(x) <= {'.', '#'} for x in r), art
    return r


def to_bytes(r):
    """7 rows of 7 columns into 8 bytes: column 0 is bit 7; column 7 and row 7 empty."""
    out = [sum(1 << (7 - c) for c in range(7) if line[c] == '#') for line in r]
    return out + [0]


def readable(r):
    return r


def mirrored(r, flags):
    if 'm' in flags:
        r = [line[::-1] for line in r]
    if 'v' in flags:
        r = r[::-1]
    return r


NAMES = [n for n, _, _ in SRC]
FLAGS = [f for _, f, _ in SRC]
READABLE = [to_bytes(rows(a)) for _, _, a in SRC]
MIRRORED = [to_bytes(mirrored(rows(a), f)) for _, f, a in SRC]
N_GLYPHS = len(SRC)
assert N_GLYPHS == 53


def ui_font():
    """Screen codes 0-63 of the upper-case Commodore-style set (8 bytes each)."""
    up = c64font.build()[0]
    return [list(up[c]) for c in range(64)]


def preview(path, scale=8):
    from PIL import Image, ImageDraw
    sets = [('readable', READABLE), ('mirrored, as the rain shows them', MIRRORED)]
    cols = 18
    rowsn = (N_GLYPHS + cols - 1) // cols
    cw = 8 * scale + 6
    W = cols * cw + 20
    H = 2 * (rowsn * cw + 40) + 10
    img = Image.new('RGB', (W, H), (2, 10, 5))
    d = ImageDraw.Draw(img)
    y0 = 10
    for title, glyphs in sets:
        d.text((10, y0), title, fill=(120, 255, 160))
        y0 += 22
        for g, rows8 in enumerate(glyphs):
            gx, gy = 10 + (g % cols) * cw, y0 + (g // cols) * cw
            d.rectangle([gx - 1, gy - 1, gx + 8 * scale, gy + 8 * scale], outline=(10, 40, 20))
            for y in range(8):
                for x in range(8):
                    if rows8[y] & (0x80 >> x):
                        d.rectangle([gx + x * scale, gy + y * scale, gx + (x + 1) * scale - 1,
                                     gy + (y + 1) * scale - 1], fill=(90, 255, 130))
        y0 += rowsn * cw + 18
    img.save(path)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else str(HERE / 'glyphs.png')
    preview(out)
    print(out, N_GLYPHS, 'glyphs')
