"""Run the MTRX RAIN launcher (BUILD/mtrx.bas) in the BASIC 65 simulator (../../tools/bas65sim.py): the
engine file loaded from the build directory, the engine itself as a scripted reply through the mailbox
(test_engine.py runs the real one). It checks the BASIC logic around the engine.

Sessions:
  from40   started in 40 x 25: the card runs out, 80 x 50, MTRX.ENG at $42000 with its signature, the
           SIDs silenced, the mailbox cleared, SYS $2000 in bank 4, the engine ends with Q; then the
           screen back to 40 x 25, border and background as found, the ending line
  from80   started in 80 x 50: no mode change before or after
  q        Q on the card: no engine, the mode back
  nofile   MTRX.ENG missing: stopped with FILE NOT FOUND, the mode back
  sixteen  the engine reports 16 colour levels: the line that says so
  wrong    the engine reports a screen that is not 80 columns
Usage: python3 test_launcher.py BUILD
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(next(p for p in (HERE.parent / 'tools', HERE.parent.parent / 'tools')
                            if (p / 'bas65sim.py').exists())))
import bas65sim as S  # noqa: E402

S.ERRORS[4] = "FILE NOT FOUND"


class M2(S.Machine):
    def __init__(self, build, width, height, missing=()):
        super().__init__(width=width, height=height)
        self.build = Path(build)
        self.missing = set(missing)
        self.bloads, self.calls = [], []
        self.d020, self.d021 = 6, 14


class I2(S.Interpreter):
    def s_BLOAD(self):
        name = self.expect('str')[1]
        addr = bank = None
        while self.peek_is('op', ','):
            self.take()
            t = self.take()
            if t == ('id', 'P'):
                (addr,) = self.args()
            elif t[0] == 'id' and t[1].startswith('B') and t[1][1:].isdigit():
                bank = int(t[1][1:])
        a = int(addr) if addr > 0xFFFF else bank * 0x10000 + int(addr)
        path = self.m.build / name
        if name in self.m.missing or not path.exists():
            raise S.BasicError(4, name)
        data = path.read_bytes()[2:]
        for i, b in enumerate(data):
            self.m.mem[a + i] = b
        self.m.bloads.append((name, a, len(data)))

    def s_FAST(self):
        pass


def run(session, build):
    width, height = (80, 50) if session == 'from80' else (40, 25)
    m = M2(build, width, height, missing=('MTRX.ENG',) if session == 'nofile' else ())
    it = I2(str(Path(build) / 'mtrx.bas'), m)
    fails = []
    seen = {}

    def hook(mm, a):
        mm.calls.append((it.bank, a))
        if it.bank != 4 or a != 0x2000:
            fails.append(f"SYS {a:X} in bank {it.bank}")
            return
        seen['mode'] = (mm.cols, mm.rows)
        seen['mailbox'] = [mm.mem.get(0x1E00 + i, 0) for i in range(5)]
        seen['sid'] = list(mm.sid)
        seen['engine'] = bytes(mm.mem.get(0x42000 + i, 0) for i in range(16))
        mm.mem[0x1E20] = {'wrong': 0x57}.get(session, 0x51)
        mm.mem[0x1E21], mm.mem[0x1E22] = 0x10, 0x27
        mm.mem[0x1E23] = 0 if session == 'sixteen' else 1
    m.sys_hook = hook
    if session == 'q':
        m.events.append({'when': lambda mm: mm.frame() > 60, 'key': ['Q'], 'delay': 0})
    try:
        it.run(max_us=60_000_000)
    except S.BasicError as e:
        fails.append(f"BASIC error {e}")
    screen = m.screen_text().replace('\n', ' ')
    calls = m.calls
    want_calls = [] if session in ('q', 'nofile') else [(4, 0x2000)]
    if calls != want_calls:
        fails.append(f"calls {calls}, expected {want_calls}")
    if want_calls:
        eng = (Path(build) / 'MTRX.ENG').read_bytes()[2:18]
        if seen.get('engine') != eng:
            fails.append("the engine not at $42000 when called")
        if seen.get('mode') != (80, 50):
            fails.append(f"the engine called in {seen.get('mode')}")
        if seen.get('mailbox') != [0, 0, 0, 0, 0]:
            fails.append(f"the mailbox {seen.get('mailbox')}")
        if any(seen.get('sid', [1])):
            fails.append("the SIDs not silenced before the call")
    if (m.cols, m.rows) != (width, height):
        fails.append(f"the screen left in {m.cols} x {m.rows}, found {width} x {height}")
    if (m.d020, m.d021) != (6, 14):
        fails.append(f"border and background {m.d020}, {m.d021}, found 6, 14")
    if any(m.sid):
        fails.append("the SIDs not silent at the end")
    expect = {'from40': "MTRX RAIN ENDED.", 'from80': "MTRX RAIN ENDED.", 'q': "MTRX RAIN ENDED.",
              'nofile': "MTRX RAIN STOPPED: FILE NOT FOUND",
              'sixteen': "THE RAIN RAN IN 16 COLOURS.", 'wrong': "MTRX RAIN NEEDS ITS 80 X 50 TEXT SCREEN."}[session]
    if expect not in screen:
        fails.append(f"not on the screen: {expect!r}")
    if session != 'sixteen' and "16 COLOURS" in screen:
        fails.append("the 16-colour line where it does not belong")
    lines = [l for l in m.screen_text().splitlines() if l.strip()]
    print(f"--- {session}: {len(m.bloads)} BLOADs, calls {calls}, {m.frame()} frames; the screen ends: "
          f"{' / '.join(l.strip() for l in lines[-2:])}")
    print("  PASS" if not fails else "  FAIL:\n    " + "\n    ".join(fails))
    return not fails


if __name__ == '__main__':
    build = sys.argv[1]
    ok = all([run(s, build) for s in ('from40', 'from80', 'q', 'nofile', 'sixteen', 'wrong')])
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)
