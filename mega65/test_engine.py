"""Run the MTRX RAIN engine in a 6502 emulator (py65 with the 45GS02 instructions it uses) against a
model of the MEGA65 parts it touches, check what it leaves on the screen, and draw it.

Modelled: CPU $0000-$1FFF bank 0, $2000-$7FFF bank 4 (BANK 4: SYS $2000), the base page register B, Z,
(zp),Z and the flat (zp),Z after the NOP prefix; chip RAM, colour RAM; the VIC-IV registers the
engine reads and writes, with the hot-register rule of viciv.vhdl (a write to $D011, $D016, $D018 or
$D031 marks the legacy registers touched; while HOTREG ($D05D bit 7) is on, a touched mark makes the
VIC-IV recompute the whole layout: here a failure; HOTREG written 0 clears the mark); $D063 bit 6
(FCOLMCM) reading back 1, or 0 on a core without it; the palette's four banks and $D070; the key
queue; the joysticks; the multiplier; the four SIDs; the frame counter (810,000 cycles a frame: 40.5
MHz, PAL) and the raster.

Checked after every run: the exit code; B, Z and the interrupt flag; every VIC-IV register, the
palette (all banks), $D070, port A as found; the SIDs silent; no write outside the engine's own
memory, the mailbox, the stack, the character set and the screen's colour bytes. At chosen frames:
every cell's colour byte is its state's colour (the white heads the head's), dark cells the
background, every code in the rain a glyph, the bar as model.bar draws it; the picture saved.
Usage: python3 test_engine.py BUILD_DIR [--png=DIR] [run names...]
"""
import sys
from pathlib import Path

from py65.devices.mpu6502 import MPU

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen_engine as E  # noqa: E402
import model as M  # noqa: E402

FRAME = 810_000
LINE = 1296
STUB = 0x1F00
CRAM0 = 0xFF80000
PHYS4 = 0x40000


def syms(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        k, v = line.split(' = ')
        out[k] = int(v[1:], 16)
    return out


class Mem:
    def __init__(self, mc):
        self.mc = mc
        self.b = 0

    @staticmethod
    def cpu2phys(a):
        if a < 0x2000:
            return a
        if a < 0x8000:
            return PHYS4 + a
        return None

    def __getitem__(self, a):
        if isinstance(a, slice):
            return [self[i] for i in range(*a.indices(0x10000))]
        if 0xD000 <= a < 0xE000:
            return self.mc.io_read(a)
        p = self.cpu2phys(a)
        if p is None:
            raise RuntimeError(f"read of ${a:04X} (PC ${self.mc.mpu.pc:04X})")
        return self.mc.ram[p]

    def __setitem__(self, a, v):
        if 0xD000 <= a < 0xE000:
            self.mc.io_write(a, v)
            return
        p = self.cpu2phys(a)
        if p is None:
            raise RuntimeError(f"write of ${a:04X} (PC ${self.mc.mpu.pc:04X})")
        self.mc.cpu_write(p, v)

    def __len__(self):
        return 0x10000


class MPU45(MPU):
    def __init__(self, memory, machine):
        self.instruct = list(MPU.instruct)
        self.cycletime = list(MPU.cycletime)
        self.extracycles = list(MPU.extracycles)
        self.mc = machine
        self.z = 0
        self.prev = 0
        self.flat = False
        super().__init__(memory=memory)
        for op, fn, cyc in ((0x5B, MPU45.op_tab, 1), (0x7B, MPU45.op_tba, 1), (0x4B, MPU45.op_taz, 1),
                            (0x6B, MPU45.op_tza, 1), (0xA3, MPU45.op_ldz, 2), (0x1B, MPU45.op_inz, 1),
                            (0xC2, MPU45.op_cpz, 2), (0x92, MPU45.op_staz, 5), (0xB2, MPU45.op_ldaz, 5)):
            self.instruct[op] = fn
            self.cycletime[op] = cyc
            self.extracycles[op] = 0

    def step(self):
        op = self.memory[self.pc]
        self.flat = self.prev == 0xEA
        if self.flat and op not in (0x92, 0xB2):
            raise RuntimeError(f"a NOP before ${op:02X} at ${self.pc:04X}: the 45GS02 would take it as a prefix")
        r = super().step()
        self.prev = op
        return r

    def bp(self, zp):
        return (self.memory.b << 8) | (zp & 0xFF)

    def ZeroPageAddr(self):
        return self.bp(self.ByteAt(self.pc))

    def ZeroPageXAddr(self):
        return self.bp(self.x + self.ByteAt(self.pc))

    def ZeroPageYAddr(self):
        return self.bp(self.y + self.ByteAt(self.pc))

    def IndirectXAddr(self):
        zp = self.x + self.ByteAt(self.pc)
        return self.ByteAt(self.bp(zp)) | (self.ByteAt(self.bp(zp + 1)) << 8)

    def IndirectYAddr(self):
        zp = self.ByteAt(self.pc)
        a1 = self.ByteAt(self.bp(zp)) | (self.ByteAt(self.bp(zp + 1)) << 8)
        return (a1 + self.y) & 0xFFFF

    def op_tab(self):
        self.memory.b = self.a

    def op_tba(self):
        self.a = self.memory.b
        self.FlagsNZ(self.a)

    def op_taz(self):
        self.z = self.a
        self.FlagsNZ(self.a)

    def op_tza(self):
        self.a = self.z
        self.FlagsNZ(self.a)

    def op_ldz(self):
        self.z = self.ByteAt(self.pc)
        self.pc += 1
        self.FlagsNZ(self.z)

    def op_inz(self):
        self.z = (self.z + 1) & 255
        self.FlagsNZ(self.z)

    def op_cpz(self):
        v = self.ByteAt(self.pc)
        self.pc += 1
        r = (self.z - v) & 0x1FF
        self.p = (self.p & ~(self.CARRY | self.ZERO | self.NEGATIVE)) | (self.CARRY if self.z >= v else 0) | \
            (self.ZERO if self.z == v else 0) | (self.NEGATIVE if r & 0x80 else 0)

    def ptr(self):
        zp = self.ByteAt(self.pc)
        self.pc += 1
        if self.flat:
            p = sum(self.ByteAt(self.bp(zp + i)) << (8 * i) for i in range(4)) & 0xFFFFFFF
            return 'flat', (p + self.z) & 0xFFFFFFF
        p = self.ByteAt(self.bp(zp)) | (self.ByteAt(self.bp(zp + 1)) << 8)
        return 'cpu', (p + self.z) & 0xFFFF

    def op_staz(self):
        kind, a = self.ptr()
        if kind == 'flat':
            self.mc.flat_write(a, self.a)
        else:
            self.memory[a] = self.a

    def op_ldaz(self):
        kind, a = self.ptr()
        self.a = self.mc.flat_read(a) if kind == 'flat' else self.memory[a]
        self.FlagsNZ(self.a)


VIC_FOUND = {0xD020: 0, 0xD021: 0, 0xD011: 0x1B, 0xD016: 0xC8, 0xD018: 0x14, 0xD031: 0xE0, 0xD054: 0x45,
             0xD058: 80, 0xD059: 0, 0xD05D: 0x81, 0xD05E: 80, 0xD060: 0x00, 0xD061: 0x08, 0xD062: 0x00,
             0xD063: 0x00, 0xD064: 0x00, 0xD065: 0x00, 0xD068: 0x00, 0xD069: 0x90, 0xD06A: 0x02}


class Machine:
    def __init__(self, build_dir, fcolmcm=True, ntsc=False, colptr=0, hot=True, mbx_flags=0, seed=0x1234,
                 limit=0, keys=(), sticks=(), chrcount=80):
        self.sym = syms(Path(build_dir) / 'engine.sym')
        eng = (Path(build_dir) / 'engine.bin').read_bytes()
        self.ram = bytearray(0x60000)
        for a in range(0x60000):
            self.ram[a] = (a * 7 + (a >> 8) * 13 + 5) & 255
        self.ram[0x42000:0x42000 + len(eng)] = eng
        self.eng_len = len(eng)
        for i, v in enumerate([0x20, 0x00, 0x20, 0xEA]):          # JSR $2000 / NOP
            self.ram[STUB + i] = v
        self.ram_found = bytes(self.ram)
        self.cram = bytearray((i * 11 + 3) & 255 for i in range(0x8000))
        self.vic = dict(VIC_FOUND)
        self.vic[0xD05D] = 0x81 if hot else 0x01
        self.vic[0xD064], self.vic[0xD065] = colptr & 255, colptr >> 8
        self.vic[0xD05E] = chrcount
        self.vic_found = dict(self.vic)
        self.touched = False
        self.fcolmcm = fcolmcm
        self.ntsc = ntsc
        self.pal = [bytearray(((bk * 97 + i * 31 + 7) & 255) for i in range(768)) for bk in range(4)]
        self.pal_found = [bytes(p) for p in self.pal]
        self.d070 = 0x10
        self.mula, self.mulb = [0] * 4, [0] * 4
        self.sid = bytearray(0x80)
        self.sid_writes = 0
        self.grains = 0
        self.dc00 = 0x7F
        self.dc00_found = self.dc00
        self.keyq = []
        self.keys = sorted(keys)                # (frame, code)
        self.sticks = sorted(sticks)            # (frame, port2 bits pressed, port1 bits pressed)
        self.joy2 = self.joy1 = 0
        self.bad = []
        self.mbx = (mbx_flags, limit & 255, limit >> 8, seed & 255, seed >> 8)
        self.colptr = colptr
        self.frame_work = []
        self.shots = {}
        self.snap = {}
        self.lit = {}
        self.hooks = {}

    # ---------------------------------------------------------------- memory
    def own(self, p):
        """The engine's own memory: from COLOUR to the base page (bank 4)."""
        return PHYS4 + E.COLOUR <= p < PHYS4 + 0x8000

    def cpu_write(self, p, v):
        ok = (0x1E00 <= p < 0x1E80) or (0x100 <= p < 0x200) or self.own(p)
        if not ok:
            self.bad.append(('cpu write', hex(p), hex(self.mpu.pc)))
        self.ram[p] = v

    def flat_read(self, a):
        if a < 0x60000:
            return self.ram[a]
        if CRAM0 <= a < CRAM0 + 0x8000:
            return self.cram[a - CRAM0]
        raise RuntimeError(f"flat read of ${a:07X} (PC ${self.mpu.pc:04X})")

    def flat_write(self, a, v):
        if E.CHARSET <= a < E.CHARSET + 2048:
            self.ram[a] = v
            return
        if CRAM0 + self.colptr <= a < CRAM0 + self.colptr + 4000:
            self.cram[a - CRAM0] = v
            return
        self.bad.append(('flat write', hex(a), hex(self.mpu.pc)))

    # ---------------------------------------------------------------- I/O
    def frame(self):
        return self.mpu.processorCycles // FRAME

    def io_write(self, a, v):
        self.check_hot()
        if 0xD770 <= a <= 0xD773:
            self.mula[a - 0xD770] = v
        elif 0xD774 <= a <= 0xD777:
            self.mulb[a - 0xD774] = v
        elif a == 0xD05D:
            self.vic[a] = v & 0xFF
            if not v & 0x80:
                self.touched = False
        elif a in (0xD011, 0xD016, 0xD018, 0xD031):
            self.vic[a] = v
            self.touched = True
        elif a == 0xD063:
            self.vic[a] = v if self.fcolmcm else v & 0xBF
        elif a in self.vic and a != 0xD05E:
            self.vic[a] = v
        elif a == 0xD070:
            self.d070 = v
        elif 0xD100 <= a < 0xD400:
            self.pal[self.d070 >> 6][a - 0xD100] = v
        elif a == 0xD610:
            if self.keyq:
                self.keyq.pop(0)
        elif a == 0xDC00:
            self.dc00 = v
        elif 0xD400 <= a < 0xD480:
            self.sid[a - 0xD400] = v
            self.sid_writes += 1
            if (a - 0xD420) % 0x40 < 0x15 and (a - 0xD420) % 0x40 % 7 == 4 and v == 0x81:
                self.grains += 1
        else:
            self.bad.append(('io write', hex(a), v, hex(self.mpu.pc)))
        self.check_hot()

    def check_hot(self):
        if self.touched and self.vic[0xD05D] & 0x80:
            self.bad.append(('the VIC-IV would recompute its layout (HOTREG on, legacy registers touched)',
                             hex(self.mpu.pc)))
            self.touched = False

    def io_read(self, a):
        pa = sum(x << (8 * i) for i, x in enumerate(self.mula))
        pb = sum(x << (8 * i) for i, x in enumerate(self.mulb))
        if 0xD778 <= a <= 0xD77F:
            return ((pa * pb) >> (8 * (a - 0xD778))) & 255
        if a == 0xD7FA:
            return self.frame() & 255
        if a == 0xD052:
            return (self.mpu.processorCycles // LINE) % 625 & 255
        if a == 0xD06F:
            return 0x80 if self.ntsc else 0x00
        if a in self.vic:
            return self.vic[a]
        if a == 0xD070:
            return self.d070
        if 0xD100 <= a < 0xD400:
            return self.pal[self.d070 >> 6][a - 0xD100]
        if a == 0xD610:
            while self.keys and self.keys[0][0] <= self.frame():
                self.keyq.append(self.keys.pop(0)[1])
            return self.keyq[0] if self.keyq else 0
        if a in (0xDC00, 0xDC01):
            while self.sticks and self.sticks[0][0] <= self.frame():
                _, self.joy2, self.joy1 = self.sticks.pop(0)
            if a == 0xDC00:
                return self.dc00 & (0xFF ^ self.joy2)
            return 0xFF ^ self.joy1 if self.dc00 == 0xFF else 0xFF
        self.bad.append(('io read', hex(a), hex(self.mpu.pc)))
        return 0

    # ---------------------------------------------------------------- what the screen shows
    def bank(self):
        return (self.d070 >> 4) & 3

    def picture(self):
        scr = self.ram[PHYS4 + E.SCREEN:PHYS4 + E.SCREEN + 4000]
        col = self.cram[self.colptr:self.colptr + 4000]
        cs = self.ram[E.CHARSET:E.CHARSET + 2048]
        p = self.pal[self.bank()]
        rgb = [(M.swap(p[i]), M.swap(p[256 + i]), M.swap(p[512 + i])) for i in range(256)]
        return bytes(scr), bytes(col), bytes(cs), rgb

    def var(self, name, n=1):
        a = self.sym[name]
        p = PHYS4 + E.BP + a if a < 0x100 else PHYS4 + a
        return sum(self.ram[p + i] << (8 * i) for i in range(n))

    def table(self, name, n):
        a = PHYS4 + self.sym[name]
        return bytes(self.ram[a:a + n])

    # ---------------------------------------------------------------- running
    def call(self, limit_steps=60_000_000, shots=(), png=None, tag='', on_frame=None):
        self.mem = Mem(self)
        self.mpu = MPU45(self.mem, self)
        self.mem.b = 0x12
        self.mpu.z = 0x34
        self.ram[0x1E00:0x1E05] = bytes(self.mbx)
        self.ram[0x1E20] = 238
        self.mpu.pc = STUB
        self.mpu.sp = 0xF0
        self.mpu.p &= ~self.mpu.INTERRUPT
        wait = self.sym['MN_W']
        shots = sorted(shots)
        steps = 0
        t0 = None
        while self.mpu.pc != STUB + 3:
            if self.mpu.pc == wait:
                fr = self.frame()
                if t0 is not None:
                    self.frame_work.append(self.mpu.processorCycles - t0)
                if shots and fr >= shots[0]:
                    self.shot(shots.pop(0), png, tag)
                if on_frame:
                    on_frame(self, fr)
                if self.mem[self.sym['LASTFC']] == fr & 255:
                    self.mpu.processorCycles = (fr + 1) * FRAME + 37
                t0 = self.mpu.processorCycles
            self.mpu.step()
            steps += 1
            if steps > limit_steps:
                raise RuntimeError(f'too long (PC ${self.mpu.pc:04X})')
        return self.ram[0x1E20], steps

    def shot(self, fr, png, tag):
        self.snap[fr] = dict({n: self.var(n) for n in E.FIELD_VARS + ['BARPG', 'NROWS', 'ND', 'HUE']},
                             TS=self.var('TS', 2),
                             drone=tuple(self.sid[o] & 1 for o in (0x04, 0x0B, 0x12, 0x44, 0x4B, 0x52)),
                             state=bytes(self.ram[PHYS4 + E.STATE:PHYS4 + E.STATE + 4000]),
                             screen=bytes(self.ram[PHYS4 + E.SCREEN:PHYS4 + E.SCREEN + 4000]),
                             chars=bytes(self.ram[E.CHARSET + 8 * M.G_STATIC:E.CHARSET + 8 * (M.G_STATIC + 53)]),
                             grains=self.grains, pal=bytes(self.pal[self.bank()]), full=self.var('FULL'),
                             mcm=self.vic[0xD016] & 0x10, fcol=self.vic[0xD063] & 0x40)
        self.shots[fr] = self.check_screen(fr)
        if png:
            scr, col, cs, rgb = self.picture()
            full = self.vic[0xD016] & 0x10
            M.render(scr, col, cs, rgb, bool(full), bool(self.vic[0xD063] & 0x40), self.vic[0xD021],
                     png=Path(png) / f'{tag}_f{fr:04d}.png', scale=2)

    def check_screen(self, fr):
        """Every cell against its state; the white heads; the bar. Returns a list of problems."""
        out = []
        scr, col, cs, rgb = self.picture()
        state = self.ram[PHYS4 + E.STATE:PHYS4 + E.STATE + 4000]
        colour = self.table('COLOUR', 256)
        chead = self.var('CHEAD')
        nrows = self.var('NROWS')
        heads = set()
        nd = self.var('ND')
        for i in range(nd):
            fl = self.ram[PHYS4 + E.D_FL + i]
            nx = self.ram[PHYS4 + E.D_NXT + i]
            if fl & E.F_HL and not fl & E.F_DEL and nx and nx - 1 < nrows and nx - 1 >= self.ram[PHYS4 + E.D_VIS + i]:
                heads.add((nx - 1) * 80 + self.ram[PHYS4 + E.D_COL + i])
        lit = 0
        for k in range(nrows * 80):
            s = state[k]
            want = chead if k in heads else colour[s]
            if col[k] != want:
                out.append(f"cell {k}: colour {col[k]} want {want} (state {s})")
            c = scr[k]
            if not (M.G_STATIC <= c < M.G_STATIC + 53 or M.G_CHANGING <= c < M.G_CHANGING + 53):
                out.append(f"cell {k}: code {c}")
            lit += s != 0
        if nrows == M.BAR_ROW:
            page = self.var('BARPG')
            vals = dict(zip(M.FIELD_ORDER, [self.var(n) for n in E.FIELD_VARS]))
            codes, lev = M.bar(page, vals)
            cmap = self.table('CMAPC', 128)
            row = 49 * 80
            if list(scr[row:row + 80]) != codes:
                out.append(f"the bar's codes differ: {list(scr[row:row + 80])[:20]}...")
            if list(col[row:row + 80]) != [cmap[x] for x in lev]:
                out.append("the bar's colours differ")
            if any(state[row:row + 80]):
                out.append("lit cells under the bar")
        self.lit[fr] = lit
        return out[:8]

    def after(self, what, want_exit):
        out = []
        if self.ram[0x1E20] != want_exit:
            out.append(f"exit ${self.ram[0x1E20]:02X}, want ${want_exit:02X}")
        if self.mem.b != 0x12 or self.mpu.z != 0x34:
            out.append(f"B ${self.mem.b:02X} Z ${self.mpu.z:02X} not as found")
        if self.mpu.p & self.mpu.INTERRUPT:
            out.append("interrupts left off")
        if self.vic != self.vic_found:
            out.append(f"VIC-IV registers {[(hex(k), v) for k, v in self.vic.items() if self.vic_found[k] != v]}")
        if any(bytes(p) != f for p, f in zip(self.pal, self.pal_found)):
            out.append("palette not as found")
        if self.d070 != 0x10:
            out.append("$D070 not as found")
        if self.dc00 != self.dc00_found:
            out.append("$DC00 not as found")
        if any(self.sid):
            out.append("the SIDs not silent")
        if self.keyq:
            out.append("keys left in the queue")
        if self.bad:
            out.append(f"stray: {self.bad[:6]}")
        for a in list(range(0x0000, 0x0100)) + list(range(0x0200, 0x1E00)) + list(range(0x1E80, 0x40000, 3)) + \
                list(range(0x40800, PHYS4 + E.COLOUR)) + list(range(0x48000, 0x60000, 5)):
            if self.ram[a] != self.ram_found[a]:
                out.append(f"memory changed at ${a:05X}")
                break
        print(f"{what}: " + ("; ".join(out) if out else "exit, registers, palette, port A, SIDs, memory as found"))
        return not out


# ---------------------------------------------------------------- the runs
def summary(mc, steps, name):
    fw = mc.frame_work[1:] or [0]
    worst = max(fw)
    print(f"  {steps} instructions, {len(mc.frame_work)} frames; work a frame: mean {sum(fw) // len(fw)} "
          f"cycles, worst {worst} ({100 * worst / FRAME:.1f} % of a frame at 40.5 MHz); "
          f"strings now {mc.var('ND')}, grains {mc.grains}")


def run(bd, name, png, expect=M.EXIT_LIMIT, shots=(), want=None, **kw):
    print(f"[{name}]")
    mc = Machine(bd, **kw)
    code, steps = mc.call(shots=shots, png=png, tag=name)
    ok = mc.after(name, expect)
    print(f"  mailbox: exit ${mc.ram[0x1E20]:02X}, frames {mc.ram[0x1E21] | mc.ram[0x1E22] << 8}, "
          f"colour levels {'128' if mc.ram[0x1E23] else '16'}")
    summary(mc, steps, name)
    for fr, probs in mc.shots.items():
        print(f"  frame {fr}: " + ("; ".join(probs) if probs else f"screen as its state says ({mc.lit[fr]} cells lit)"))
        ok &= not probs
    if want:
        for fr, check, what in want:
            r = check(mc.snap)
            print(f"  {'ok  ' if r else 'FAIL'} {what}")
            ok &= bool(r)
    return ok, mc


MIRRORED = bytes(b for rows8 in M.G.MIRRORED for b in rows8)


def theme_pal(name, pal):
    """The theme's 128 levels where the engine puts them."""
    planes = M.theme_planes(name)
    return all(pal[k * 256 + M.full_index(L)] == planes[k][L] for k in range(3) for L in range(128))


def rainbow_pal(snap):
    """RAINBOW at the engine's hue, 128 levels where the engine puts them."""
    planes = M.rainbow_planes(snap['HUE'])
    return all(snap['pal'][k * 256 + M.full_index(L)] == planes[k][L] for k in range(3) for L in range(128))


def rainbow_pal_fb(snap):
    planes = M.rainbow_planes_fb(snap['HUE'])
    return all(snap['pal'][k * 256 + e] == planes[k][e] for k in range(3) for e in range(16))


SPACE, Q, P, K, S = 0x20, 0x51, 0x70, 0x6B, 0x73
RIGHT, LEFT, UP, DOWN = 0x1D, 0x9D, 0x91, 0x11
ON, OFF = (1,) * 6, (0,) * 6


def main():
    bd = Path(sys.argv[1])
    args = sys.argv[2:]
    png = next((a.split('=', 1)[1] for a in args if a.startswith('--png=')), None)
    if png:
        Path(png).mkdir(parents=True, exist_ok=True)
    names = [a for a in args if not a.startswith('--')]
    runs = {
        # 10 s of rain, the defaults (35 %, density 50 %, GREEN, sound and humm); pictures as it fills
        'glass': dict(limit=500, shots=(50, 150, 300, 499),
                      want=[(0, lambda s: s[499]['full'] == 1 and s[499]['mcm'] and s[499]['fcol'],
                             'MCM and FCOLMCM on: 128 levels'),
                            (0, lambda s: s[50]['SPI'] == M.SPEED0 and s[50]['DNI'] == M.DENS0 and s[50]['THEME'] == 0
                             and s[50]['SMODE'] == M.SOUND0 and s[50]['drone'] == ON,
                             'starts at 35 %, density 50 %, GREEN, sound and humm'),
                            (0, lambda s: s[499]['chars'] == MIRRORED, 'the glyphs mirrored')]),
        # every key: speed, a palette, time stopped and run, the bar's pages, the four sound modes,
        # density, round the palettes to RAINBOW and back to GREEN; Q
        'keys': dict(limit=0, expect=M.EXIT_QUIT,
                     shots=(55, 120, 175, 195, 220, 245, 285, 330, 345, 358, 365, 378, 385, 398, 405, 430, 455, 520,
                            545),
                     keys=[(60, RIGHT), (62, RIGHT), (100, P), (150, SPACE), (200, SPACE), (240, K), (280, K),
                           (320, K), (340, S), (360, S), (380, S), (400, S), (420, DOWN), (425, DOWN), (440, P),
                           (445, P), (450, P), (540, P), (560, Q)],
                     want=[(0, lambda s: s[55]['SPI'] == M.SPEED0 and s[120]['SPI'] == M.SPEED0 + 2,
                            'right twice: 35 % to 70 %'),
                           (0, lambda s: theme_pal('GREEN', s[55]['pal']) and theme_pal('AMBER', s[120]['pal']),
                            'P: GREEN, then AMBER in the palette'),
                           (0, lambda s: s[175]['TIMEF'] == 1 and s[175]['TS'] == 0 and s[175]['state'] == s[195]['state']
                            and s[175]['screen'] == s[195]['screen'], 'SPACE: time stopped, nothing changes'),
                           (0, lambda s: s[220]['TIMEF'] == 0 and s[220]['TS'] == 256 and s[220]['state'] != s[195]['state'],
                            'SPACE again: time runs (back to full speed)'),
                           (0, lambda s: s[245]['BARPG'] == 1 and s[285]['BARPG'] == 2 and s[285]['NROWS'] == 50
                            and s[330]['BARPG'] == 0 and s[330]['NROWS'] == M.BAR_ROW, 'K: keys, no bar, values'),
                           (0, lambda s: s[345]['SMODE'] == 3 and s[345]['drone'] == OFF
                            and s[358]['grains'] == s[345]['grains'], 'S: no sound (no humm, no grains)'),
                           (0, lambda s: s[365]['SMODE'] == 0 and s[365]['drone'] == OFF
                            and s[378]['grains'] > s[365]['grains'], 'S: the sound (grains, no humm)'),
                           (0, lambda s: s[385]['SMODE'] == 1 and s[385]['drone'] == ON
                            and s[398]['grains'] == s[385]['grains'], 'S: the humm (no grains)'),
                           (0, lambda s: s[405]['SMODE'] == 2 and s[405]['drone'] == ON, 'S: both again'),
                           (0, lambda s: s[430]['DNI'] == M.DENS0 - 2, 'down twice: density 30 %'),
                           (0, lambda s: s[455]['THEME'] == M.T_RAINBOW and s[455]['HUE'] < 16 and rainbow_pal(s[455])
                            and rainbow_pal(s[520]) and s[520]['HUE'] > s[455]['HUE'],
                            'P three times: RAINBOW from green, its hue moving on'),
                           (0, lambda s: s[545]['THEME'] == 0 and theme_pal('GREEN', s[545]['pal']),
                            'P again: back to GREEN')]),
        # the sticks: port 2 right (speed), port 1 up (density), port 2 fire (time) twice; RUN/STOP
        'sticks': dict(limit=0, expect=M.EXIT_QUIT, shots=(100, 160),
                       sticks=[(40, 8, 0), (45, 0, 0), (60, 0, 1), (65, 0, 0), (80, 16, 0), (85, 0, 0),
                               (120, 16, 0), (125, 0, 0)], keys=[(170, 0x03)],
                       want=[(0, lambda s: s[160]['SPI'] == M.SPEED0 + 1 and s[160]['DNI'] == M.DENS0 + 1,
                              'port 2 right: speed up; port 1 up: density up'),
                             (0, lambda s: s[100]['TIMEF'] == 1 and s[160]['TIMEF'] == 0, 'fire: time stops, fire: runs')]),
        # a core without FCOLMCM: 16 colours, no MCM; RAINBOW in 16 colours
        'fallback': dict(limit=300, fcolmcm=False, shots=(90, 200, 299), keys=[(100, P), (105, P), (110, P), (115, P)],
                         want=[(0, lambda s: max(s[90]['state']) > 0 and s[299]['full'] == 0 and not s[299]['mcm'],
                                'rain with 16 colours, MCM never set'),
                               (0, lambda s: s[200]['THEME'] == M.T_RAINBOW and rainbow_pal_fb(s[200])
                                and rainbow_pal_fb(s[299]) and s[299]['HUE'] != s[200]['HUE'],
                                'RAINBOW in the 16 colours, moving on')]),
        # HOTREG off as found, the colour RAM at offset $0800, NTSC, no sound from the start
        'variants': dict(limit=250, hot=False, colptr=0x0800, ntsc=True, mbx_flags=1, shots=(249,),
                         want=[(0, lambda s: s[249]['SMODE'] == 3 and s[249]['drone'] == OFF and s[249]['grains'] == 0,
                                'no sound from the start')]),
        # 250 %, density 100 %, RAINBOW: the busiest frame
        'busy': dict(limit=400, keys=[(1, RIGHT)] * 7 + [(2, UP)] * 4 + [(3, P)] * 4, shots=(399,),
                     want=[(0, lambda s: s[399]['SPI'] == 8 and s[399]['DNI'] == 7 and rainbow_pal(s[399]),
                            '250 %, density 100 %, RAINBOW')]),
        # not an 80-column screen: nothing touched
        'mode': dict(limit=10, chrcount=40, expect=M.EXIT_MODE),
    }
    ok = True
    for name, kw in runs.items():
        if names and name not in names:
            continue
        r, _ = run(bd, name, png, **kw)
        ok &= r
    print("ALL PASS" if ok else "FAILURES")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
