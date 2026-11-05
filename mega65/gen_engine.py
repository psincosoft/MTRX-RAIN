"""Write the MTRX RAIN engine's assembly source (GLASS: the rain on the screen, 80 x 50 text).

Plain NMOS 6502 opcodes; the 45GS02's own (TAB TBA TAZ TZA LDZ INZ CPZ, LDA/STA (zp),Z, and the flat
32-bit (zp),Z with the NOP prefix) as .byte. Called by BASIC with BANK 4: SYS $2000 (bank 4 at CPU
$2000-$7FFF = $42000-$47FFF, bank 0 below, I/O at $D000). Interrupts off while it runs; the base page
at $7F00 (B = $7F); B and Z as found on return. model.py is the specification.

Mailbox ($1E00), BASIC to the engine: $1E00 flags (bit 0 no sound, bit 1 the 16-colour fallback even
where FCOLMCM is there: tests), $1E01-$1E02 a frame limit (tests; 0 none), $1E03-$1E04 a seed (0: from
the frame counter and the raster). The engine to BASIC: $1E20 how it ended ($51 Q, $4C the frame limit,
$57 not an 80-column screen), $1E21-$1E22 frames, $1E23 1 with 128 colour levels, 0 with 16.

The screen: the VIC-IV is pointed at our own screen ($46F00, 80 x 50 codes) and character set
($40000); the colour RAM stays where BASIC has it (its offset read from $D064). With FCOLMCM the
multicolour bit of $D016 is set, with HOTREG held off around the write so that the VIC-IV does not
recompute the 80 x 50 layout (viciv.vhdl: a touched legacy register recomputes it while HOTREG is on).
Everything is put back on the way out, the palette bank too.
Usage: python3 gen_engine.py OUT.asm
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import glyphs as G  # noqa: E402
import model as M  # noqa: E402

# ---------------------------------------------------------------- the layout (CPU addresses, bank 4)
ENGINE = 0x2000
CODE_LIMIT = 0x3100
T_NEXT, T_LEVEL, T_POOL, T_VTAB, T_SWAP = 0x3100, 0x3200, 0x3300, 0x3400, 0x3500
T_WHEELR, T_WHEELG, T_WHEELB = 0x3600, 0x3700, 0x3800
T_CMAPF, T_CMAPB, T_RBW, T_RBK = 0x3900, 0x3980, 0x3A00, 0x3A80
T_ROWL, T_ROWH = 0x3B00, 0x3B40
T_TRL, T_TRH, T_CRT, T_DTHR = 0x3B80, 0x3BA0, 0x3BC0, 0x3BE0
T_RBWF, T_RBKF, T_DRONEON, T_GRAINON = 0x3C00, 0x3C10, 0x3C20, 0x3C24
T_BAR0C, T_BAR0L, T_BAR1C, T_BAR1L = 0x3C40, 0x3C90, 0x3CE0, 0x3D30
T_FIELDS = 0x3D80                       # the bar's fields, to $3E7F
T_PALS = 0x3E80                         # 4 themes x 3 planes x 128 levels
T_PALFB = 0x4480                        # 4 themes x 3 planes x 16
T_SOUND = 0x4540                        # the drone's frequencies, the grains'
T_UIFONT, T_GLYM = 0x4600, 0x4800
DATA_END = 0x4A00
COLOUR = 0x5100                         # from here on nothing is loaded: the engine's own memory
D_COL, D_YL, D_YH, D_NXT, D_V, D_FL, D_VIS, D_GAP = (0x5200 + 0x100 * i for i in range(8))
LAST = 0x5A00
VARS = 0x5B00
SAVEPAL = 0x5C00
STATE = 0x5F00                          # 4,000 cells, cleared to $6EFF (16 pages)
SCREEN = 0x6F00                         # 4,000 codes, the VIC-IV's screen ($46F00)
SCREEN_END = SCREEN + 4000
BP = 0x7F00
PHYS = 0x40000
CHARSET = 0x40000
MAILBOX = 0x1E00
assert DATA_END <= COLOUR
assert STATE + 0x1000 == SCREEN and SCREEN_END <= BP

F_HL, F_DEL, F_CHG = 0x04, 0x08, 0x10
P256 = {k: round(v * 256) for k, v in (('hl', M.P_HL), ('del', M.P_DEL), ('chg', M.P_CHG),
                                       ('rndchg', M.P_RNDCHG), ('vis', M.P_VIS))}

# the SIDs (memory map: 1 and 2 right, 3 and 4 left; music on 1 and 3, effects on 2 and 4)
SID = [0xD400, 0xD420, 0xD440, 0xD460]
SID_CLOCK = 984375.0
DRONE_HZ = [55.0, 82.41, 27.5]
DETUNE = 1.0035


def sid_freq(hz):
    return round(hz * 16777216 / SID_CLOCK)


DRONE_R = [sid_freq(h) for h in DRONE_HZ]
DRONE_L = [sid_freq(h * DETUNE) for h in DRONE_HZ]
DRONE_WAVE = [0x10, 0x40, 0x10]         # triangle, pulse, triangle
DRONE_AD = [0x90, 0x90, 0xA0]
DRONE_SR = [0xA9, 0x79, 0xC9]
GRAIN_F = [0x2800 + g * 0x2A0 for g in range(G.N_GLYPHS)]
GRAIN_AD, GRAIN_SR = 0x01, 0x01
VOL_DRONE, VOL_GRAIN = 0x0C, 0x09

# ---------------------------------------------------------------- variables
BPV = [('SP', 2), ('CP', 4), ('SCP', 2), ('PS', 2), ('PSC', 2), ('PCR', 4), ('FP', 4), ('TP', 2), ('TL', 2),
       ('PR', 2), ('PG2', 2), ('PB', 2), ('RNG', 2), ('TMP', 2), ('CNT', 2), ('PG', 1), ('ROW', 1), ('COL', 1),
       ('CUR', 1), ('OFF', 2), ('STV', 1), ('GLY', 1), ('FI', 1), ('CNTB', 1), ('JNOW', 1), ('JHIT', 1)]
AV = ['SAVB', 'SAVZ', 'S020', 'S021', 'S016', 'S054', 'S058', 'S059', 'S05D', 'S060', 'S061', 'S062', 'S063',
      'S068', 'S069', 'S06A', 'S070', 'SDC00', 'MFLAGS', ('FLIMIT', 2), ('FRAMES', 2), 'LASTFC', 'FULL',
      'NTOFF', ('COLBASE', 4), 'ND', 'NROWS', 'QUITF', 'BARDIRTY', 'BARPG', 'RCNT', ('STMT', 2), 'JPREV',
      ('TS', 2), ('TACC', 2), ('CACC', 2), 'CHEAD', 'TT', 'GRAINR', 'GRAINL', 'GVR', 'GVL', 'GOFFR', 'GOFFL',
      'PWPH', ('INC16', 2), 'NT', 'EXCODE', 'HUE', 'HUEPAL', 'WR', 'WG', 'WB', 'TR', 'TG', 'TB',
      # the bar's values, in model.FIELD_ORDER: speed, density, theme, time, sound
      'SPI', 'DNI', 'THEME', 'TIMEF', 'SMODE',
      ('CMAPC', 128)]


def alloc():
    out, a = {}, 0
    for name, n in BPV:
        out[name] = a
        a += n
    assert a <= 0x100, f"base page {a} bytes"
    a = VARS
    for v in AV:
        name, n = (v, 1) if isinstance(v, str) else v
        out[name] = a
        a += n
    assert a <= VARS + 0x100, f"vars {a - VARS}"
    return out


SYM = alloc()
FIELD_VARS = ['SPI', 'DNI', 'THEME', 'TIMEF', 'SMODE']
assert len(FIELD_VARS) == len(M.FIELD_ORDER)
assert [SYM[n] for n in FIELD_VARS] == list(range(SYM['SPI'], SYM['SPI'] + len(FIELD_VARS)))

HW = """
BORDER = $D020
SCREENC = $D021
VCTRL = $D054
LSTEPL = $D058
LSTEPH = $D059
HOTREG = $D05D
CHRCNT = $D05E
SCRP0 = $D060
SCRP1 = $D061
SCRP2 = $D062
SCRP3 = $D063
COLPL = $D064
COLPH = $D065
CHRP0 = $D068
CHRP1 = $D069
CHRP2 = $D06A
VIDMODE = $D06F
PALSEL = $D070
PALR = $D100
PALG = $D200
PALB = $D300
LEGACY = $D016
RASTL = $D052
KEYQ = $D610
FRAMEC = $D7FA
CIAPA = $DC00
CIAPB = $DC01
MULA0 = $D770
MULA1 = $D771
MULA2 = $D772
MULA3 = $D773
MULB0 = $D774
MULB1 = $D775
MULB2 = $D776
MULB3 = $D777
MULO0 = $D778
MULO1 = $D779
MULO2 = $D77A
"""


# ---------------------------------------------------------------- 45GS02 helpers
def tab():
    return "        .byte $5B               ; TAB"


def tba():
    return "        .byte $7B               ; TBA"


def taz():
    return "        .byte $4B               ; TAZ"


def tza():
    return "        .byte $6B               ; TZA"


def ldz(v):
    return f"        .byte $A3, {v}          ; LDZ #{v}"


def inz():
    return "        .byte $1B               ; INZ"


def cpz(v):
    return f"        .byte $C2, {v}          ; CPZ #{v}"


def ldaz(zp):
    return f"        .byte $B2, {zp}         ; LDA ({zp}),Z"


def staz(zp):
    return f"        .byte $92, {zp}         ; STA ({zp}),Z"


def staf(zp):
    return f"        .byte $EA, $92, {zp}    ; STA [{zp}],Z (flat)"


def ldaf(zp):
    return f"        .byte $EA, $B2, {zp}    ; LDA [{zp}],Z (flat)"


def ld16(dst, v):
    return f"        LDA #<({v})\n        STA {dst}\n        LDA #>({v})\n        STA {dst}+1"


def mov(dst, src, n):
    return "\n".join(f"        LDA {src}+{i}\n        STA {dst}+{i}" for i in range(n))


def lines(*parts):
    return "\n".join(p for p in parts if p is not None)


# ---------------------------------------------------------------- start and exit
def code_start():
    return f"""
* = $2000
        JMP START
        .byte $4D, $54, $52, VERSION        ; "MTR" and the version: BASIC checks them
        .fill 25, 0

; ======================================================================
; START: BASIC's call. B and Z kept, the base page at $7F00, the mailbox read, the screen checked
; (80 columns), the VIC-IV's registers and palette saved, ours set, the rain started.
; ======================================================================
START:  SEI
        CLD
{tba()}
        TAX
{tza()}
        TAY
        LDA #$7F
{tab()}
        TXA
        PHA
        TYA
        PHA
        LDA #0
        TAX
ST_CLR: STA $00,X
        STA VARS,X
        INX
        BNE ST_CLR
        PLA
        STA SAVZ
        PLA
        STA SAVB
        LDA MAILBOX
        STA MFLAGS
        LDA MAILBOX+1
        STA FLIMIT
        LDA MAILBOX+2
        STA FLIMIT+1
        LDA MAILBOX+3
        STA RNG
        LDA MAILBOX+4
        STA RNG+1
        ORA RNG
        BNE ST_1
        LDA FRAMEC
        STA RNG+1
        LDA RASTL
        EOR #$5A
        STA RNG
        ORA RNG+1
        BNE ST_1
        LDA #$A5
        STA RNG
ST_1:   LDA CHRCNT
        CMP #80
        BEQ ST_2
        LDA #EXIT_MODE
        JMP EXIT0
ST_2:   LDA #0
        STA NTOFF
        LDA VIDMODE
        BPL ST_3
        LDA #{len(M.SPEEDS)}
        STA NTOFF
ST_3:   LDA CIAPA
        STA SDC00
        JSR VICSAVE
        JSR CLEAR
        JSR MODETEST
        JSR PALSET
        JSR CHARS
        LDA COLOUR
        JSR COLFILL
        JSR VICSET
        LDA #{M.SPEED0}
        STA SPI
        LDA #{M.DENS0}
        STA DNI
        LDA #{M.BAR_ROW}
        STA NROWS
        LDA #1
        STA TS+1
        LDA #128
        STA RCNT
        LDA #200
        STA STMT
        LDA #{M.SOUND0}
        STA SMODE
        LDA MFLAGS
        AND #1
        BEQ ST_4
        LDA #3
        STA SMODE
ST_4:   JSR BARDRAW
        JSR SNDINIT
        LDA FRAMEC
        STA LASTFC

; ======================================================================
; MAIN: once a frame (the frame counter): the keys and the sticks, time's scale, the ticks due, the
; glyph changes due, the white heads, RAINBOW's colours, the bar, the sound.
; ======================================================================
MAIN:
MN_W:   LDA FRAMEC
        CMP LASTFC
        BEQ MN_W
        STA LASTFC
        INC FRAMES
        BNE MN_0
        INC FRAMES+1
MN_0:   JSR INPUT
        LDA QUITF
        BEQ MN_1
        LDA #EXIT_QUIT
        JMP EXIT
MN_1:   LDA FLIMIT
        ORA FLIMIT+1
        BEQ MN_2
        LDA FRAMES+1
        CMP FLIMIT+1
        BCC MN_2
        BNE MN_L
        LDA FRAMES
        CMP FLIMIT
        BCC MN_2
MN_L:   LDA #EXIT_LIMIT
        JMP EXIT
MN_2:   JSR TIMESC
        JSR TICKS
        JSR CYCLES
        JSR HEADS
        LDA THEME
        CMP #{M.T_RAINBOW}
        BNE MN_4
        LDA HUE
        CMP HUEPAL
        BEQ MN_4
        JSR RAINBOW
MN_4:   LDA BARDIRTY
        BEQ MN_3
        LDA #0
        STA BARDIRTY
        JSR BARDRAW
MN_3:   JSR SOUND
MN_END: JMP MAIN

; EXIT: A is the exit code. Silence, the VIC-IV and the palette as found, port A as found; EXIT0:
; the mailbox, the key queue emptied, Z and B as found.
EXIT:   STA EXCODE
        JSR SNDOFF
        JSR VICBACK
        LDA SDC00
        STA CIAPA
        LDA EXCODE
EXIT0:  STA MAILBOX+$20
        LDA FRAMES
        STA MAILBOX+$21
        LDA FRAMES+1
        STA MAILBOX+$22
        LDA FULL
        STA MAILBOX+$23
EX_K:   LDA KEYQ
        BEQ EX_R
        STA KEYQ
        JMP EX_K
EX_R:   LDA SAVZ
{taz()}
        LDA SAVB
{tab()}
        CLI
        RTS
"""


# ---------------------------------------------------------------- the screen
def code_screen():
    return f"""
; ======================================================================
; VICSAVE: the registers the engine changes, and the palette bank the text is shown from.
; MODETEST: FCOLMCM set and read back: FULL 1 (128 levels) or 0 (16 colours); the colour map and the
; state colours made for it. VICSET: our screen, characters, line step, MCM. VICBACK: all as found.
; ======================================================================
VICSAVE: LDA BORDER
        STA S020
        LDA SCREENC
        STA S021
        LDA LEGACY
        STA S016
        LDA VCTRL
        STA S054
        LDA LSTEPL
        STA S058
        LDA LSTEPH
        STA S059
        LDA HOTREG
        STA S05D
        LDA SCRP0
        STA S060
        LDA SCRP1
        STA S061
        LDA SCRP2
        STA S062
        LDA SCRP3
        STA S063
        LDA CHRP0
        STA S068
        LDA CHRP1
        STA S069
        LDA CHRP2
        STA S06A
        LDA COLPL
        STA COLBASE
        LDA COLPH
        STA COLBASE+1
        LDA #$F8
        STA COLBASE+2
        LDA #$0F
        STA COLBASE+3
        LDA PALSEL
        STA S070
        JSR PALMAP
        LDX #0
VSV_P:  LDA PALR,X
        STA SAVEPAL,X
        LDA PALG,X
        STA SAVEPAL+$100,X
        LDA PALB,X
        STA SAVEPAL+$200,X
        INX
        BNE VSV_P
        RTS

; PALMAP: the bank the CPU edits ($D070 bits 7-6) := the bank the text is shown from (bits 5-4)
PALMAP: LDA S070
        AND #$3F
        STA TMP
        LDA S070
        AND #$30
        ASL A
        ASL A
        ORA TMP
        STA PALSEL
        RTS

MODETEST: LDA #0
        STA FULL
        LDA MFLAGS
        AND #2
        BNE MT_1
        LDA S063
        ORA #$40
        STA SCRP3
        LDA SCRP3
        AND #$40
        BEQ MT_1
        LDA #1
        STA FULL
MT_1:   LDX #127
MT_C:   LDA FULL
        BEQ MT_F
        LDA CMAPF,X
        JMP MT_2
MT_F:   LDA CMAPB,X
MT_2:   STA CMAPC,X
        DEX
        BPL MT_C
        LDX #0
MT_S:   LDY LEVEL,X
        LDA CMAPC,Y
        STA COLOUR,X
        INX
        BNE MT_S
        LDY #{M.L_HEAD}
        LDA CMAPC,Y
        STA CHEAD
        RTS

VICSET: LDA #<({PHYS + SCREEN})
        STA SCRP0
        LDA #>(({PHYS + SCREEN}) & $FFFF)
        STA SCRP1
        LDA #({PHYS + SCREEN} >> 16)
        STA SCRP2
        LDA SCRP3
        AND #$F0
        STA SCRP3
        LDA #80
        STA LSTEPL
        LDA #0
        STA LSTEPH
        LDA #<{CHARSET}
        STA CHRP0
        LDA #>({CHARSET} & $FFFF)
        STA CHRP1
        LDA #({CHARSET} >> 16)
        STA CHRP2
        LDA S054
        AND #$F8
        STA VCTRL
        LDA #0
        STA BORDER
        STA SCREENC
        LDA FULL
        BEQ VS_X
        LDA S016
        ORA #$10
        JSR WD016
VS_X:   RTS

; WD016: A into $D016 with HOTREG off; the touched mark it leaves cancelled before HOTREG is put back
WD016:  STA TMP
        LDA S05D
        AND #$7F
        STA HOTREG
        LDA TMP
        STA LEGACY
        LDA S05D
        AND #$7F
        STA HOTREG
        LDA S05D
        STA HOTREG
        RTS

VICBACK: LDA FULL
        BEQ VB_1
        LDA S016
        JSR WD016
VB_1:   LDA S054
        STA VCTRL
        LDA S058
        STA LSTEPL
        LDA S059
        STA LSTEPH
        LDA S060
        STA SCRP0
        LDA S061
        STA SCRP1
        LDA S062
        STA SCRP2
        LDA S063
        STA SCRP3
        LDA S068
        STA CHRP0
        LDA S069
        STA CHRP1
        LDA S06A
        STA CHRP2
        LDA S020
        STA BORDER
        LDA S021
        STA SCREENC
        JSR PALMAP
        LDX #0
VB_P:   LDA SAVEPAL,X
        STA PALR,X
        LDA SAVEPAL+$100,X
        STA PALG,X
        LDA SAVEPAL+$200,X
        STA PALB,X
        INX
        BNE VB_P
        LDA S070
        STA PALSEL
        RTS

; PALSET: the theme's colours into the palette: 128 levels (FULL) or the 16 of the fallback
PALSET: LDA THEME
        CMP #{M.T_RAINBOW}
        BNE PS_0
        JMP RAINBOW
PS_0:   ASL A
        TAX
        LDA FULL
        BEQ PS_F
        LDA PALTL,X
        STA PR
        LDA PALTL+1,X
        STA PR+1
        CLC
        LDA PR
        ADC #128
        STA PG2
        LDA PR+1
        ADC #0
        STA PG2+1
        CLC
        LDA PG2
        ADC #128
        STA PB
        LDA PG2+1
        ADC #0
        STA PB+1
        LDY #0
PS_L:   LDX CMAPF,Y
        LDA (PR),Y
        STA PALR,X
        LDA (PG2),Y
        STA PALG,X
        LDA (PB),Y
        STA PALB,X
        INY
        BPL PS_L
        RTS
PS_F:   LDA PALTF,X
        STA PR
        LDA PALTF+1,X
        STA PR+1
        CLC
        LDA PR
        ADC #16
        STA PG2
        LDA PR+1
        ADC #0
        STA PG2+1
        CLC
        LDA PG2
        ADC #16
        STA PB
        LDA PG2+1
        ADC #0
        STA PB+1
        LDY #0
PS_M:   LDA (PR),Y
        STA PALR,Y
        LDA (PG2),Y
        STA PALG,Y
        LDA (PB),Y
        STA PALB,Y
        INY
        CPY #16
        BNE PS_M
        RTS
PALTL:  .word {', '.join(f'${T_PALS + 384 * t:04X}' for t in range(len(M.STATIC_THEMES)))}
PALTF:  .word {', '.join(f'${T_PALFB + 48 * t:04X}' for t in range(len(M.STATIC_THEMES)))}

; RAINBOW: the palette at HUE: each level's colour W + wheel x K / 256 a channel (the multiplier's
; bits 8-15), nybble-swapped (SWAP); 128 levels, or the fallback's 16 entries
RAINBOW: LDA HUE
        STA HUEPAL
        TAX
        LDA WHEELR,X
        STA WR
        LDA WHEELG,X
        STA WG
        LDA WHEELB,X
        STA WB
        LDA #0
        STA MULA1
        STA MULA2
        STA MULA3
        STA MULB1
        STA MULB2
        STA MULB3
        LDA FULL
        BNE RB_0
        JMP RB_F
RB_0:   LDY #0
RB_L:   LDA RBK,Y
        STA MULB0
        LDA WR
        STA MULA0
        LDA MULO1
        CLC
        ADC RBW,Y
        TAX
        LDA SWAP,X
        STA TR
        LDA WG
        STA MULA0
        LDA MULO1
        CLC
        ADC RBW,Y
        TAX
        LDA SWAP,X
        STA TG
        LDA WB
        STA MULA0
        LDA MULO1
        CLC
        ADC RBW,Y
        TAX
        LDA SWAP,X
        STA TB
        LDX CMAPF,Y
        LDA TR
        STA PALR,X
        LDA TG
        STA PALG,X
        LDA TB
        STA PALB,X
        INY
        BPL RB_L
        RTS
RB_F:   LDY #0
RB_M:   LDA RBKF,Y
        STA MULB0
        LDA WR
        STA MULA0
        LDA MULO1
        CLC
        ADC RBWF,Y
        TAX
        LDA SWAP,X
        STA PALR,Y
        LDA WG
        STA MULA0
        LDA MULO1
        CLC
        ADC RBWF,Y
        TAX
        LDA SWAP,X
        STA PALG,Y
        LDA WB
        STA MULA0
        LDA MULO1
        CLC
        ADC RBWF,Y
        TAX
        LDA SWAP,X
        STA PALB,Y
        INY
        CPY #16
        BNE RB_M
        RTS

; CHARS: the bar's letters (codes 0-63) and the rain's glyphs (mirrored) into the
; character set at $40000, the glyphs twice (static from 128, changing from 192).
CHARS:  LDA #<{T_UIFONT}
        STA TP
        LDA #>{T_UIFONT}
        STA TP+1
        LDA #0
        STA FP
        LDA #>({CHARSET} & $FFFF)
        STA FP+1
        LDA #({CHARSET} >> 16)
        STA FP+2
        LDA #0
        STA FP+3
{ld16('CNT', 512)}
        JSR FCOPY
        LDA #{M.G_STATIC}
        JSR GLYSET
        LDA #{M.G_CHANGING}
GLYSET: STA TMP
        LDA #<{T_GLYM}
        STA TP
        LDA #>{T_GLYM}
        STA TP+1
        LDA TMP
        ASL A
        ASL A
        ASL A
        STA FP
        LDA TMP
        LSR A
        LSR A
        LSR A
        LSR A
        LSR A
        CLC
        ADC #>({CHARSET} & $FFFF)
        STA FP+1
        LDA #({CHARSET} >> 16)
        STA FP+2
        LDA #0
        STA FP+3
{ld16('CNT', 8 * G.N_GLYPHS)}

; FCOPY: CNT bytes from TP (the CPU's map) to FP (flat)
FCOPY:
{ldz(0)}
FC_L:   LDA CNT
        ORA CNT+1
        BEQ FC_X
{ldaz('TP')}
{staf('FP')}
        INC TP
        BNE FC_1
        INC TP+1
FC_1:   INC FP
        BNE FC_2
        INC FP+1
        BNE FC_2
        INC FP+2
FC_2:   LDA CNT
        BNE FC_3
        DEC CNT+1
FC_3:   DEC CNT
        JMP FC_L
FC_X:   RTS

; COLFILL: the 4,000 colour bytes of the screen to A
COLFILL: STA TMP
{mov('FP', 'COLBASE', 4)}
{ld16('CNT', 4000)}
{ldz(0)}
CF_L:   LDA TMP
{staf('FP')}
        INC FP
        BNE CF_1
        INC FP+1
        BNE CF_1
        INC FP+2
CF_1:   LDA CNT
        BNE CF_2
        DEC CNT+1
CF_2:   DEC CNT
        LDA CNT
        ORA CNT+1
        BNE CF_L
        RTS

; CLEAR: every cell dark, no strings, every column free; the screen full of glyphs nobody sees yet
CLEAR:  LDA #<{STATE}
        STA SP
        LDA #>{STATE}
        STA SP+1
        LDA #<{SCREEN}
        STA SCP
        LDA #>{SCREEN}
        STA SCP+1
        LDX #16
{ldz(0)}
CL_P:   LDA #0
{staz('SP')}
        JSR RAND
        TAY
        LDA POOL,Y
        CLC
        ADC #{M.G_STATIC}
{staz('SCP')}
{inz()}
        BNE CL_P
        INC SP+1
        INC SCP+1
        DEX
        BNE CL_P
        LDX #79
        LDA #$FF
CL_L:   STA LAST,X
        DEX
        BPL CL_L
        LDA #0
        STA ND
        RTS

; CELLP: ROW, COL into PS (the state), PSC (the screen) and PCR (the colour byte, flat)
CELLP:  LDX ROW
        CLC
        LDA ROWL,X
        ADC COL
        STA OFF
        STA PS
        STA PSC
        LDA ROWH,X
        ADC #0
        STA OFF+1
        CLC
        ADC #>{STATE}
        STA PS+1
        LDA OFF+1
        CLC
        ADC #>{SCREEN}
        STA PSC+1
        CLC
        LDA OFF
        ADC COLBASE
        STA PCR
        LDA OFF+1
        ADC COLBASE+1
        STA PCR+1
        LDA COLBASE+2
        ADC #0
        STA PCR+2
        LDA COLBASE+3
        STA PCR+3
        RTS
"""


# ---------------------------------------------------------------- the rain
def code_rain():
    rows_vis = 31
    return f"""
; ======================================================================
; TIMESC: time's scale TS (0-256) a step towards its target (256 running, 0 stopped): an eighth of
; the way a frame, at least 6/256 (about 0.4 s either way). TICKS: the ticks this frame owes (the
; speed's rate times TS); a tick ages every cell (DECAY), moves the strings (DROPS), starts new ones
; (SPAWN), counts to the stammer.
; ======================================================================
TIMESC: LDA TIMEF
        BNE TS_DN
        LDA TS+1
        BNE TS_X
        LDA TS
        LSR A
        LSR A
        LSR A
        STA TMP
        SEC
        LDA #32
        SBC TMP
        CMP #6
        BCS TS_U
        LDA #6
TS_U:   CLC
        ADC TS
        STA TS
        BCC TS_X
        LDA #1
        STA TS+1
        LDA #0
        STA TS
TS_X:   RTS
TS_DN:  LDA TS+1
        BEQ TS_D1
        LDA #0
        STA TS+1
        LDA #224
        STA TS
        RTS
TS_D1:  LDA TS
        BEQ TS_X
        LSR A
        LSR A
        LSR A
        CMP #6
        BCS TS_D2
        LDA #6
TS_D2:  STA TMP
        LDA TS
        CMP TMP
        BCS TS_D3
        LDA #0
        STA TS
        RTS
TS_D3:  SBC TMP
        STA TS
        RTS

; RATE: A:X (16-bit rate, X high) times TS, over 256, into INC16
RATE:   STA MULA0
        STX MULA1
        LDA #0
        STA MULA2
        STA MULA3
        STA MULB2
        STA MULB3
        LDA TS
        STA MULB0
        LDA TS+1
        STA MULB1
        LDA MULO1
        STA INC16
        LDA MULO2
        STA INC16+1
        RTS

TICKS:  LDA SPI
        CLC
        ADC NTOFF
        TAY
        LDA TRL,Y
        LDX TRH,Y
        JSR RATE
        CLC
        LDA TACC
        ADC INC16
        STA TACC
        LDA TACC+1
        ADC INC16+1
        CMP #3
        BCC TK_1
        LDA #3
TK_1:   STA TACC+1
TK_L:   LDA TACC+1
        BEQ TK_X
        DEC TACC+1
        JSR TICK
        JMP TK_L
TK_X:   RTS

TICK:   JSR DECAY
        JSR DROPS
        JSR SPAWN
        LDA STMT
        BNE TC_1
        DEC STMT+1
TC_1:   DEC STMT
        LDA STMT
        ORA STMT+1
        BNE TC_X
        JMP STAMMER
TC_X:   RTS

; STAMMER: every white head a row behind (it holds for a row); the next one in 125 to 380 ticks
STAMMER: LDX #0
SM_L:   CPX ND
        BCS SM_X
        LDA D_FL,X
        AND #{F_HL}
        BEQ SM_N
        LDA D_YH,X
        BEQ SM_N
        DEC D_YH,X
SM_N:   INX
        JMP SM_L
SM_X:   JSR RAND
        CLC
        ADC #125
        STA STMT
        LDA #0
        ADC #0
        STA STMT+1
        RTS

; CYCLES: the glyph changes owed (8 a second at speed 100 %, times the speed's root, times TS)
CYCLES: LDA SPI
        CLC
        ADC NTOFF
        TAY
        LDA CRT,Y
        LDX #0
        JSR RATE
        CLC
        LDA CACC
        ADC INC16
        STA CACC
        LDA CACC+1
        ADC INC16+1
        BEQ CC_X
        LDA #0
        STA CACC+1
        JMP CYCLE
CC_X:   RTS

; ======================================================================
; DECAY: every lit cell a tick older (NEXT), its colour byte from its new state (COLOUR); dark cells
; are skipped. 15 pages and 160 cells.
; ======================================================================
DECAY:  LDA #<{STATE}
        STA SP
        LDA #>{STATE}
        STA SP+1
{mov('CP', 'COLBASE', 4)}
        LDA #15
        STA PG
DC_P:
{ldz(0)}
DC_L:
{ldaz('SP')}
        BEQ DC_N
        TAX
        LDA NEXT,X
{staz('SP')}
        TAX
        LDA COLOUR,X
{staf('CP')}
DC_N:
{inz()}
        BNE DC_L
        INC SP+1
        INC CP+1
        BNE DC_1
        INC CP+2
DC_1:   DEC PG
        BNE DC_P
{ldz(0)}
DC_M:
{ldaz('SP')}
        BEQ DC_O
        TAX
        LDA NEXT,X
{staz('SP')}
        TAX
        LDA COLOUR,X
{staf('CP')}
DC_O:
{inz()}
{cpz(4000 - 15 * 256)}
        BNE DC_M
        RTS

; ======================================================================
; DROPS: each string falls by its speed; each row it reaches is written (WRITE); a string past the
; last row is removed (REMOVE: the last string moves into its place, LAST kept right).
; ======================================================================
DROPS:  LDX #0
DR_L:   CPX ND
        BCC DR_1
        RTS
DR_1:   STX CUR
        CLC
        LDA D_YL,X
        ADC D_V,X
        STA D_YL,X
        LDA D_YH,X
        ADC #0
        STA D_YH,X
DR_W:   LDX CUR
        LDA D_YH,X
        CMP D_NXT,X
        BCC DR_E
        LDA D_NXT,X
        CMP NROWS
        BCS DR_S
        JSR WRITE
DR_S:   LDX CUR
        INC D_NXT,X
        JMP DR_W
DR_E:   LDA NROWS
        CMP D_NXT,X
        BCS DR_K
        JSR REMOVE
        LDX CUR
        JMP DR_L
DR_K:   INX
        JMP DR_L

; WRITE: string CUR reaches row D_NXT. An eraser darkens the cell; any other string, once past its
; invisible lead, lights it (its class's first state) with a new glyph (changing if the string is,
; or one cell in twelve), and a white head asks for a grain (left or right by the column).
WRITE:  LDX CUR
        LDA D_NXT,X
        STA ROW
        LDA D_COL,X
        STA COL
        LDA D_FL,X
        AND #{F_DEL}
        BEQ WR_1
        JSR CELLP
{ldz(0)}
        LDA #0
{staz('PS')}
        LDA COLOUR
{staf('PCR')}
        RTS
WR_1:   LDA ROW
        CMP D_VIS,X
        BCS WR_2
        RTS
WR_2:   JSR CELLP
        LDX CUR
        LDA D_FL,X
        AND #3
        TAY
        LDA CLS1,Y
        STA STV
{ldz(0)}
{staz('PS')}
        JSR RAND
        TAY
        LDA POOL,Y
        STA GLY
        LDX CUR
        LDA D_FL,X
        AND #{F_CHG}
        BNE WR_C
        JSR RAND
        CMP #{P256['rndchg']}
        BCC WR_C
        LDA GLY
        CLC
        ADC #{M.G_STATIC}
        JMP WR_3
WR_C:   LDA GLY
        CLC
        ADC #{M.G_CHANGING}
WR_3:
{ldz(0)}
{staz('PSC')}
        LDX STV
        LDA COLOUR,X
{staf('PCR')}
        LDX CUR
        LDA D_FL,X
        AND #{F_HL}
        BEQ WR_X
        LDA GLY
        ORA #$80
        LDY COL
        CPY #40
        BCS WR_R
        STA GRAINL
        RTS
WR_R:   STA GRAINR
WR_X:   RTS
CLS1:   .byte {', '.join(str(M.first_state(c)) for c in range(4))}

REMOVE: LDX CUR
        LDY D_COL,X
        TXA
        CMP LAST,Y
        BNE RM_1
        LDA #$FF
        STA LAST,Y
RM_1:   DEC ND
        LDY ND
        CPY CUR
        BEQ RM_X
        LDA D_COL,Y
        STA D_COL,X
        LDA D_YL,Y
        STA D_YL,X
        LDA D_YH,Y
        STA D_YH,X
        LDA D_NXT,Y
        STA D_NXT,X
        LDA D_V,Y
        STA D_V,X
        LDA D_FL,Y
        STA D_FL,X
        LDA D_VIS,Y
        STA D_VIS,X
        LDA D_GAP,Y
        STA D_GAP,X
        LDY D_COL,X
        LDA LAST,Y
        CMP ND
        BNE RM_X
        TXA
        STA LAST,Y
RM_X:   RTS

; ======================================================================
; SPAWN: each free column (no string, or the last one GAP rows down) starts a string with the
; density's chance. NEWDROP: its speed (never faster than the string ahead, so they never meet), its
; class, a white head (1 in 5), an eraser (1 in 14), changing glyphs (1 in 8), an invisible lead.
; ======================================================================
SPAWN:  LDA #0
        STA COL
SP_L:   LDA ND
        CMP #{M.MAXD}
        BCS SP_X
        LDY COL
        LDX LAST,Y
        CPX #$FF
        BEQ SP_1
        LDA D_GAP,X
        CMP D_NXT,X
        BCS SP_N
SP_1:   JSR RAND
        LDY DNI
        CMP DTHR,Y
        BCS SP_N
        JSR NEWDROP
SP_N:   INC COL
        LDA COL
        CMP #80
        BCC SP_L
SP_X:   RTS

NEWDROP: LDX ND
        LDA COL
        STA D_COL,X
        LDA #0
        STA D_YL,X
        STA D_YH,X
        STA D_NXT,X
        STA D_VIS,X
        JSR RAND
        TAY
        LDA VTAB,Y
        STA D_V,X
        LDY COL
        LDA LAST,Y
        CMP #$FF
        BEQ ND_1
        TAY
        LDA D_V,Y
        CMP D_V,X
        BCS ND_1
        STA D_V,X
ND_1:   JSR RAND
        AND #3
        STA D_FL,X
        JSR RAND
        CMP #{P256['hl']}
        BCS ND_2
        LDA D_FL,X
        ORA #{F_HL}
        STA D_FL,X
ND_2:   JSR RAND
        CMP #{P256['del']}
        BCS ND_3
        LDA D_FL,X
        ORA #{F_DEL}
        STA D_FL,X
        JMP ND_4
ND_3:   JSR RAND
        CMP #{P256['chg']}
        BCS ND_5
        LDA D_FL,X
        ORA #{F_CHG}
        STA D_FL,X
ND_5:   JSR RAND
        CMP #{P256['vis']}
        BCS ND_4
        JSR RAND
        AND #{rows_vis}
        STA D_VIS,X
ND_4:   JSR RAND
        AND #15
        CLC
        ADC #{M.GAP_MIN}
        STA D_GAP,X
        LDY COL
        TXA
        STA LAST,Y
        INC ND
        INC HUE
        RTS

; ======================================================================
; CYCLE: the glyph changes: every cell bright enough whose glyph is a changing one gets a new one (all
; on the same tick); a static one now and then (one in about 200).
; ======================================================================
CYCLE:  LDA #<{STATE}
        STA SP
        LDA #>{STATE}
        STA SP+1
        LDA #<{SCREEN}
        STA SCP
        LDA #>{SCREEN}
        STA SCP+1
        LDA #16
        STA PG
CY_P:
{ldz(0)}
CY_L:
{ldaz('SP')}
        BEQ CY_N
        TAX
        LDA LEVEL,X
        CMP #{M.LEVEL_LIT}
        BCC CY_N
{ldaz('SCP')}
        CMP #{M.G_CHANGING}
        BCS CY_C
        DEC RCNT
        BNE CY_N
        JSR RAND
        ORA #$80
        STA RCNT
        JSR RAND
        TAY
        LDA POOL,Y
        CLC
        ADC #{M.G_STATIC}
{staz('SCP')}
        JMP CY_N
CY_C:   JSR RAND
        TAY
        LDA POOL,Y
        CLC
        ADC #{M.G_CHANGING}
{staz('SCP')}
CY_N:
{inz()}
        BNE CY_L
        INC SP+1
        INC SCP+1
        DEC PG
        BNE CY_P
        RTS

; HEADS: the white heads painted over their cells (after the tick's colours)
HEADS:  LDX #0
HD_L:   CPX ND
        BCS HD_X
        LDA D_FL,X
        AND #{F_HL | F_DEL}
        CMP #{F_HL}
        BNE HD_N
        LDA D_NXT,X
        BEQ HD_N
        SEC
        SBC #1
        CMP NROWS
        BCS HD_N
        CMP D_VIS,X
        BCC HD_N
        STA ROW
        LDA D_COL,X
        STA COL
        STX CUR
        JSR CELLP
{ldz(0)}
        LDA CHEAD
{staf('PCR')}
        LDX CUR
HD_N:   INX
        JMP HD_L
HD_X:   RTS

; RAND: xorshift (7, 9, 8) on RNG; A the high byte (X, Y, Z untouched)
RAND:   LDA RNG+1
        LSR A
        LDA RNG
        ROR A
        EOR RNG+1
        STA RNG+1
        ROR A
        EOR RNG
        STA RNG
        EOR RNG+1
        STA RNG+1
        RTS
"""


# ---------------------------------------------------------------- input and the bar
def code_input():
    return f"""
; ======================================================================
; INPUT: the key queue ($D610, a key at a time, popped), then both joysticks (a press each):
; left and right the speed, up and down the density, fire the time.
; ======================================================================
INPUT:
IN_K:   LDA KEYQ
        BEQ IN_J
        STA KEYQ
        JSR KEYDO
        JMP IN_K
IN_J:   LDA #$FF
        STA CIAPA
        LDA CIAPA
        EOR #$FF
        AND #$1F
        STA TMP
        LDA CIAPB
        EOR #$FF
        AND #$1F
        ORA TMP
        STA JNOW
        LDA JPREV
        EOR #$FF
        AND JNOW
        STA JHIT
        LDA JNOW
        STA JPREV
        LDA JHIT
        AND #1
        BEQ IJ_1
        JSR DENSUP
IJ_1:   LDA JHIT
        AND #2
        BEQ IJ_2
        JSR DENSDN
IJ_2:   LDA JHIT
        AND #4
        BEQ IJ_3
        JSR SPDDN
IJ_3:   LDA JHIT
        AND #8
        BEQ IJ_4
        JSR SPDUP
IJ_4:   LDA JHIT
        AND #16
        BEQ IJ_5
        JSR TIMETG
IJ_5:   RTS

KEYDO:  STA TMP
        LDX #0
KD_L:   LDA KEYS,X
        BEQ KD_X
        CMP TMP
        BEQ KD_GO
        INX
        JMP KD_L
KD_GO:  TXA
        ASL A
        TAX
        LDA KACT,X
        STA TP
        LDA KACT+1,X
        STA TP+1
        JMP (TP+{BP})
KD_X:   RTS
"""


def keys_table():
    k = [(0x51, 'QUIT'), (0x71, 'QUIT'), (0x03, 'QUIT'), (0x1B, 'QUIT'), (0x20, 'TIMETG'),
         (0x1D, 'SPDUP'), (0x9D, 'SPDDN'), (0x91, 'DENSUP'), (0x11, 'DENSDN'),
         (0x50, 'THEMEN'), (0x70, 'THEMEN'), (0x53, 'SOUNDTG'), (0x73, 'SOUNDTG'),
         (0x4B, 'BARPAGE'), (0x6B, 'BARPAGE')]
    return k


def code_actions():
    k = keys_table()
    return f"""
KEYS:   .byte {', '.join(f'${c:02X}' for c, _ in k)}, 0
KACT:   .word {', '.join(a for _, a in k)}

QUIT:   LDA #1
        STA QUITF
AC_R:   RTS
TIMETG: LDA TIMEF
        EOR #1
        STA TIMEF
        JMP DIRTY
SPDUP:  LDA SPI
        CMP #{len(M.SPEEDS) - 1}
        BCS AC_R
        INC SPI
        JMP DIRTY
SPDDN:  LDA SPI
        BEQ AC_R
        DEC SPI
        JMP DIRTY
DENSUP: LDA DNI
        CMP #{len(M.DENSITIES) - 1}
        BCS AC_X
        INC DNI
        JMP DIRTY
DENSDN: LDA DNI
        BEQ AC_X
        DEC DNI
        JMP DIRTY
THEMEN: LDA THEME
        CLC
        ADC #1
        CMP #{len(M.THEME_ORDER)}
        BCC TH_1
        LDA #0
TH_1:   STA THEME
        CMP #{M.T_RAINBOW}
        BNE TH_2
        LDA #0
        STA HUE
TH_2:   JSR PALSET
        JMP DIRTY
SOUNDTG: LDA SMODE
        CLC
        ADC #1
        AND #3
        STA SMODE
        JSR SNDGATE
        JMP DIRTY
BARPAGE: LDA BARPG
        CLC
        ADC #1
        CMP #3
        BCC BP_1
        LDA #0
BP_1:   STA BARPG
        CMP #2
        BNE BP_2
        LDA #50
        STA NROWS
        JMP BARHIDE
BP_2:   CMP #0
        BNE DIRTY
        LDA #{M.BAR_ROW}
        STA NROWS
        JSR BARCLR
DIRTY:  LDA #1
        STA BARDIRTY
AC_X:   RTS

; ======================================================================
; The bar on row 49: BARDRAW draws the page (0 the values, 1 the keys) from its template and puts the
; values into their fields; BARCLR darkens the row's cells (the bar comes back); BARHIDE gives the
; row back to the rain (glyphs nobody sees, dark).
; ======================================================================
BARDRAW: LDA BARPG
        CMP #2
        BCC BD_0
        RTS
BD_0:   LDA #{M.BAR_ROW}
        STA ROW
        LDA #0
        STA COL
        JSR CELLP
        LDA BARPG
        BNE BD_1
{ld16('TP', T_BAR0C)}
{ld16('TL', T_BAR0L)}
        JMP BD_2
BD_1:
{ld16('TP', T_BAR1C)}
{ld16('TL', T_BAR1L)}
BD_2:
{ldz(0)}
BD_L:
{ldaz('TP')}
{staz('PSC')}
{ldaz('TL')}
        TAX
        LDA CMAPC,X
{staf('PCR')}
{inz()}
{cpz(80)}
        BNE BD_L
        LDA BARPG
        BEQ BD_F
        RTS
BD_F:   LDA #0
        STA FI
BF_L:   LDX FI
        LDA SPI,X
        CLC
        ADC FBASE,X
        TAY
        LDA FPTRL,Y
        STA TP
        LDA FPTRH,Y
        STA TP+1
        LDA FCOL,X
        STA COL
        LDA FWID,X
        STA CNTB
        JSR CELLP
{ldz(0)}
BF_C:
{ldaz('TP')}
{staz('PSC')}
{inz()}
        DEC CNTB
        BNE BF_C
        INC FI
        LDA FI
        CMP #{len(M.FIELD_ORDER)}
        BCC BF_L
        RTS

BARCLR: LDA #{M.BAR_ROW}
        STA ROW
        LDA #0
        STA COL
        JSR CELLP
{ldz(0)}
BC_L:   LDA #0
{staz('PS')}
{inz()}
{cpz(80)}
        BNE BC_L
        RTS

BARHIDE: LDA #{M.BAR_ROW}
        STA ROW
        LDA #0
        STA COL
        JSR CELLP
{ldz(0)}
BH_L:   LDA #0
{staz('PS')}
        JSR RAND
        TAY
        LDA POOL,Y
        CLC
        ADC #{M.G_STATIC}
{staz('PSC')}
        LDA COLOUR
{staf('PCR')}
{inz()}
{cpz(80)}
        BNE BH_L
        RTS
"""


# ---------------------------------------------------------------- sound
def code_sound():
    r, l = SID[0], SID[2]
    gr, gl = SID[1], SID[3]
    init = []
    for s in SID:
        init.append(f"        LDX #24\n        LDA #0\nSI_{s:04X}: STA ${s:04X},X\n        DEX\n        BPL SI_{s:04X}")
    for base in (r, l):
        for v in range(3):
            o = base + 7 * v
            init.append(f"        LDA #${DRONE_AD[v]:02X}\n        STA ${o + 5:04X}\n        LDA #${DRONE_SR[v]:02X}\n"
                        f"        STA ${o + 6:04X}")
        init.append(f"        LDA #8\n        STA ${base + 3:04X}\n        STA ${base + 10:04X}\n        STA ${base + 17:04X}")
        init.append(f"        LDA #{VOL_DRONE}\n        STA ${base + 0x18:04X}")
    for base in (gr, gl):
        for v in range(3):
            o = base + 7 * v
            init.append(f"        LDA #${GRAIN_AD:02X}\n        STA ${o + 5:04X}\n        LDA #${GRAIN_SR:02X}\n"
                        f"        STA ${o + 6:04X}")
        init.append(f"        LDA #{VOL_GRAIN}\n        STA ${base + 0x18:04X}")
    gate = []
    for base in (r, l):
        for v in range(3):
            gate.append(f"        LDA #${DRONE_WAVE[v]:02X}\n        ORA TMP\n        STA ${base + 7 * v + 4:04X}")
    drone = []
    for side, base, tab in (('R', r, 'DRNR'), ('L', l, 'DRNL')):
        for v in range(3):
            drone.append(f"""        LDA {tab}+{2 * v}
        STA MULA0
        LDA {tab}+{2 * v + 1}
        STA MULA1
        LDA MULO1
        STA ${base + 7 * v:04X}
        LDA MULO2
        STA ${base + 7 * v + 1:04X}""")
    return f"""
; ======================================================================
; Sound. The humm, a drone on SIDs 1 (right) and 3 (left): A1, E2 (a pulse, its width breathing) and
; A0, the left a shade sharp; it drops an octave as time stops. The sound, grains on SIDs 2 (right) and
; 4 (left): a short noise tick when a white head lights a cell, its pitch the glyph's, its side the
; column's; one a frame a side, three voices in turn. SMODE: 0 the sound, 1 the humm, 2 both, 3 none.
; Filters off.
; ======================================================================
SNDINIT:
{chr(10).join(init)}
SNDGATE: LDY SMODE
        LDA DRONEON,Y
        STA TMP
{chr(10).join(gate)}
        RTS

SNDOFF: LDX #$7F
        LDA #0
SO_L:   STA $D400,X
        DEX
        BPL SO_L
        RTS

SOUND:  LDX GOFFR
        BEQ SD_A
        LDA #$80
        STA ${gr - 7 + 4:04X},X
        LDA #0
        STA GOFFR
SD_A:   LDX GOFFL
        BEQ SD_B
        LDA #$80
        STA ${gl - 7 + 4:04X},X
        LDA #0
        STA GOFFL
SD_B:   LDY SMODE
        LDA DRONEON,Y
        BNE SD_ON
        JMP SD_G
SD_ON:  LDA #0
        STA MULA2
        STA MULA3
        STA MULB2
        STA MULB3
        LDA TS+1
        LSR A
        LDA TS
        ROR A
        CLC
        ADC #128
        STA MULB0
        LDA #0
        ADC #0
        STA MULB1
{chr(10).join(drone)}
        INC PWPH
        LDA PWPH
        BPL SD_2
        EOR #$7F
SD_2:   AND #$7F
        STA TMP
        LDA #0
        STA TMP+1
        ASL TMP
        ROL TMP+1
        ASL TMP
        ROL TMP+1
        ASL TMP
        ROL TMP+1
        CLC
        LDA TMP
        ADC #$00
        STA ${r + 9:04X}
        STA ${l + 9:04X}
        LDA TMP+1
        ADC #$02
        STA ${r + 10:04X}
        STA ${l + 10:04X}
SD_G:   LDY SMODE
        LDA GRAINON,Y
        BEQ SD_6
        LDA GRAINR
        BPL SD_5
        AND #$7F
        TAY
        LDX GVR
        JSR GVNEXT
        STX GVR
        STX GOFFR
        LDA GRFL,Y
        STA ${gr - 7:04X},X
        LDA GRFH,Y
        STA ${gr - 7 + 1:04X},X
        LDA #$81
        STA ${gr - 7 + 4:04X},X
SD_5:   LDA GRAINL
        BPL SD_6
        AND #$7F
        TAY
        LDX GVL
        JSR GVNEXT
        STX GVL
        STX GOFFL
        LDA GRFL,Y
        STA ${gl - 7:04X},X
        LDA GRFH,Y
        STA ${gl - 7 + 1:04X},X
        LDA #$81
        STA ${gl - 7 + 4:04X},X
SD_6:   LDA #0
        STA GRAINR
        STA GRAINL
        RTS

; GVNEXT: X the next grain voice's offset: 7, 14, 21 (the voice's registers at SID-7+X)
GVNEXT: TXA
        CLC
        ADC #7
        CMP #22
        BCC GV_1
        LDA #7
GV_1:   TAX
        RTS
"""


# ---------------------------------------------------------------- the tables
def data(name, vals, per=16):
    vals = list(vals)
    out = [f"{name}:"] if name else []
    for i in range(0, len(vals), per):
        out.append("        .byte " + ", ".join(f"${v & 255:02X}" for v in vals[i:i + per]))
    return "\n".join(out)


def at(addr, name, vals):
    return f"* = ${addr:04X}\n" + data(name, vals)


def bar_fields():
    """The fields' strings, their pointer tables and descriptors, at T_FIELDS."""
    fcol, fwid, fbase, ptr, strings = [], [], [], [], []
    a = T_FIELDS + len(M.FIELD_ORDER) * 3
    for name in M.FIELD_ORDER:
        col, w, vals = M.FIELDS[name]
        fcol.append(col)
        fwid.append(w)
        fbase.append(len(ptr))
        for v in vals:
            ptr.append(None)
    a += 2 * len(ptr)
    k = 0
    for name in M.FIELD_ORDER:
        col, w, vals = M.FIELDS[name]
        for v in vals:
            ptr[k] = a
            strings += M.scr(v)
            a += w
            k += 1
    assert a <= T_PALS, f"the fields run to ${a:04X}"
    return "\n".join([
        f"* = ${T_FIELDS:04X}",
        data('FCOL', fcol), data('FWID', fwid), data('FBASE', fbase),
        data('FPTRL', [p & 255 for p in ptr]), data('FPTRH', [p >> 8 for p in ptr]),
        data('FSTR', strings)])


def code_tables():
    b0c, b0l = M.bar_template(0)
    b1c, b1l = M.bar_template(1)
    trl = [M.tick_rate(s, 50) for s in M.SPEEDS] + [M.tick_rate(s, 60) for s in M.SPEEDS]
    crt = [M.cycle_rate(s, 50) for s in M.SPEEDS] + [M.cycle_rate(s, 60) for s in M.SPEEDS]
    pals = []
    for name in M.STATIC_THEMES:
        for plane in M.theme_planes(name):
            pals += list(plane)
    palfb = []
    for name in M.STATIC_THEMES:
        for plane in M.theme_planes_fb(name):
            palfb += list(plane)
    snd = []
    for v in range(3):
        snd += [DRONE_R[v] & 255, DRONE_R[v] >> 8]
    for v in range(3):
        snd += [DRONE_L[v] & 255, DRONE_L[v] >> 8]
    uif = [b for rows8 in G.ui_font() for b in rows8]
    glym = [b for rows8 in G.MIRRORED for b in rows8]
    return "\n".join([
        "CODE_END:",
        at(T_NEXT, 'NEXT', M.NEXT),
        at(T_LEVEL, 'LEVEL', M.LEVEL),
        at(T_POOL, 'POOL', M.POOL),
        at(T_VTAB, 'VTAB', M.VTAB),
        at(T_SWAP, 'SWAP', [M.swap(v) for v in range(256)]),
        at(T_WHEELR, 'WHEELR', [c[0] for c in M.WHEEL]),
        at(T_WHEELG, 'WHEELG', [c[1] for c in M.WHEEL]),
        at(T_WHEELB, 'WHEELB', [c[2] for c in M.WHEEL]),
        at(T_CMAPF, 'CMAPF', M.CMAP_FULL),
        at(T_CMAPB, 'CMAPB', M.CMAP_FB),
        at(T_RBW, 'RBW', M.RB_W),
        at(T_RBK, 'RBK', M.RB_K),
        at(T_ROWL, 'ROWL', [(r * 80) & 255 for r in range(50)]),
        at(T_ROWH, 'ROWH', [(r * 80) >> 8 for r in range(50)]),
        at(T_TRL, 'TRL', [t & 255 for t in trl]),
        at(T_TRH, 'TRH', [t >> 8 for t in trl]),
        at(T_CRT, 'CRT', crt),
        at(T_DTHR, 'DTHR', [M.dens_threshold(d) for d in M.DENSITIES]),
        at(T_RBWF, 'RBWF', M.RB_WF),
        at(T_RBKF, 'RBKF', M.RB_KF),
        at(T_DRONEON, 'DRONEON', M.DRONE_ON),
        at(T_GRAINON, 'GRAINON', M.GRAIN_ON),
        at(T_BAR0C, 'BAR0C', b0c), at(T_BAR0L, 'BAR0L', b0l),
        at(T_BAR1C, 'BAR1C', b1c), at(T_BAR1L, 'BAR1L', b1l),
        bar_fields(),
        at(T_PALS, 'PALS', pals),
        at(T_PALFB, 'PALFB', palfb),
        at(T_SOUND, 'DRNR', snd[:6]),
        data('DRNL', snd[6:]),
        data('GRFL', [f & 255 for f in GRAIN_F]),
        data('GRFH', [f >> 8 for f in GRAIN_F]),
        at(T_UIFONT, 'UIFONT', uif),
        at(T_GLYM, 'GLYM', glym),
        "TABLES_END:",
    ])


def consts():
    s = [f"VERSION = {M.VERSION}", f"EXIT_QUIT = ${M.EXIT_QUIT:02X}", f"EXIT_LIMIT = ${M.EXIT_LIMIT:02X}",
         f"EXIT_MODE = ${M.EXIT_MODE:02X}", f"MAILBOX = ${MAILBOX:04X}", f"VARS = ${VARS:04X}",
         f"COLOUR = ${COLOUR:04X}", f"LAST = ${LAST:04X}", f"SAVEPAL = ${SAVEPAL:04X}",
         f"STATE = ${STATE:04X}", f"SCREEN = ${SCREEN:04X}"]
    for name, a in zip(['D_COL', 'D_YL', 'D_YH', 'D_NXT', 'D_V', 'D_FL', 'D_VIS', 'D_GAP'],
                       [D_COL, D_YL, D_YH, D_NXT, D_V, D_FL, D_VIS, D_GAP]):
        s.append(f"{name} = ${a:04X}")
    for k, v in SYM.items():
        s.append(f"{k} = ${v:04X}")
    return "\n".join(s)


def code():
    return "\n".join([consts(), HW, code_start(), code_screen(), code_rain(), code_input(), code_actions(),
                      code_sound(), code_tables()]) + "\n"


def main():
    Path(sys.argv[1]).write_text(code())


if __name__ == '__main__':
    main()
