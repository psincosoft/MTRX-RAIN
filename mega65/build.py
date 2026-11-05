"""Build MTRX RAIN for the MEGA65: the engine, the BASIC program, the disk.
Usage: python3 build.py OUT_DIR

Steps: gen_engine.py assembled (../../tools/asm65.py) into MTRX.ENG, checked: the signature, the code
below its limit and the tables below the engine's own memory, no absolute access below $2000 but the
mailbox, no NOP anywhere but as the prefix of a flat (zp),Z (the 45GS02 would take any NOP before an
(zp),Z instruction as the prefix); mtrx.b65 with the opening card (../../psinco-card/psinco-card.b65)
preprocessed (bas65pp, lines of up to 160 characters), linted, tokenised and listed back; the D81
written with the program first (LOAD"*"), AUTOBOOT.C65, the engine and the listing (SEQ), then
checked file by file.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# the tools and the card: beside this folder, or two folders up
TOOLS = next(p for p in (HERE.parent / 'tools', HERE.parent.parent / 'tools') if (p / 'asm65.py').exists())
CARD = next(p for p in (HERE / 'psinco-card.b65', HERE.parent.parent / 'psinco-card' / 'psinco-card.b65')
            if p.exists())
sys.path.insert(0, str(HERE))
import gen_engine as E  # noqa: E402
import model as M  # noqa: E402

DISK_NAME, DISK_ID, DISK_FILE = 'MTRX RAIN', 'MR', 'MTRX-RAIN.D81'
ABSOP = {0x0D, 0x2D, 0x4D, 0x6D, 0x8D, 0xAD, 0xCD, 0xED, 0x1D, 0x3D, 0x5D, 0x7D, 0x9D, 0xBD, 0xDD, 0xFD, 0x19, 0x39,
         0x59, 0x79, 0x99, 0xB9, 0xD9, 0xF9, 0x0E, 0x2E, 0x4E, 0x6E, 0x8E, 0xAE, 0xCE, 0xEE, 0x8C, 0xAC, 0xCC, 0xEC,
         0x2C, 0x1E, 0x3E, 0x5E, 0x7E, 0xDE, 0xFE, 0xBE, 0xBC, 0x9C, 0x9E, 0x4C, 0x20, 0x6C}


def run(*cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{' '.join(str(c) for c in cmd)}\n{r.stdout}{r.stderr}")
    return r.stdout


def engine(out):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'engine.asm').write_text(E.code())
    run('python3', TOOLS / 'asm65.py', out / 'engine.asm', out / 'engine.bin', out / 'engine.lst', out / 'engine.sym')
    eng = (out / 'engine.bin').read_bytes()
    sym = dict(l.split(' = ') for l in (out / 'engine.sym').read_text().splitlines())
    assert eng[3:6] == M.SIGNATURE and eng[6] == M.VERSION, 'signature'
    end = int(sym['CODE_END'][1:], 16)
    assert end <= E.CODE_LIMIT, f'the code runs to ${end:04X}, past ${E.CODE_LIMIT:04X}'
    tend = int(sym['TABLES_END'][1:], 16)
    assert tend <= E.DATA_END, f'the tables run to ${tend:04X}, past ${E.DATA_END:04X}'
    bad, nops = [], []
    for line in (out / 'engine.lst').read_text().splitlines():
        m = re.match(r'\s*([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{2}\s)+)\s*(.*)', line)
        if not m:
            continue
        pc = int(m.group(1), 16)
        by = [int(x, 16) for x in m.group(2).split()]
        text = m.group(3)
        if pc >= end or text.lower().startswith('.byte') and 'nop' not in text.lower() and \
                not re.search(r';\s*(LDZ|INZ|CPZ|TAB|TBA|TAZ|TZA|LDA|STA)', text):
            continue
        if len(by) == 3 and by[0] in ABSOP:
            a = by[1] | by[2] << 8
            if a < 0x2000 and not 0x1E00 <= a < 0x1E80:
                bad.append(line.strip())
        if by[0] == 0xEA and not (len(by) == 3 and by[1] in (0x92, 0xB2)):
            nops.append(line.strip())
    assert not bad, 'absolute accesses below $2000:\n' + '\n'.join(bad)
    assert not nops, 'a NOP that the 45GS02 would take as a prefix:\n' + '\n'.join(nops)
    (out / 'MTRX.ENG').write_bytes(bytes([0x00, 0x20]) + eng)
    return eng, sym


def basic(out):
    shutil.copy(HERE / 'mtrx.b65', out / 'mtrx.b65')
    shutil.copy(CARD, out / 'psinco-card.b65')
    run('python3', TOOLS / 'bas65pp.py', out / 'mtrx.b65', out / 'mtrx.bas', '--width', '160')
    r = subprocess.run(['python3', str(TOOLS / 'lint_basic.py'), str(out / 'mtrx.bas')], capture_output=True,
                       text=True)
    probs = re.findall(r"'([^']*)'", r.stdout.split('problems:', 1)[1]) if 'problems:' in r.stdout else []
    real = [x for x in probs if not (re.fullmatch(r'\d+: (\d+) characters', x)
                                     and int(re.fullmatch(r'\d+: (\d+) characters', x).group(1)) <= 160)]
    if real:
        sys.exit(f"lint: {real}")
    run('python3', TOOLS / 'bas65tok.py', out / 'mtrx.bas', out / 'mtrx.prg')
    back = run('python3', TOOLS / 'bas65tok.py', '--list', out / 'mtrx.prg')
    assert back == (out / 'mtrx.bas').read_text(), 'the tokenised program does not list back as written'
    return (out / 'mtrx.prg').read_bytes()


def main():
    out = Path(sys.argv[1])
    eng, sym = engine(out)
    print(f"MTRX.ENG {len(eng) + 2} bytes, code to {sym['CODE_END']}, tables to {sym['TABLES_END']}")
    prg = basic(out)
    print(f"mtrx.prg {len(prg)} bytes (to ${0x2001 + len(prg) - 2:04X}), "
          f"{len((out / 'mtrx.bas').read_text().splitlines())} lines")
    disk = out / DISK_FILE
    entries = [('MTRX RAIN', out / 'mtrx.prg', 'prg'), ('AUTOBOOT.C65', out / 'mtrx.prg', 'prg'),
               ('MTRX.ENG', out / 'MTRX.ENG', 'prg'), ('MTRX.BAS', out / 'mtrx.bas', 'listing')]
    run('python3', TOOLS / 'make_d81.py', '--disk', disk, DISK_NAME, DISK_ID, *[f"{n}={p}:{k}" for n, p, k in entries])
    print(run('python3', TOOLS / 'check_d81.py', disk, *[f"{n}={p}" for n, p, k in entries if k == 'prg']).strip())


if __name__ == '__main__':
    main()
