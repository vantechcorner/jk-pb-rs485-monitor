# SPDX-License-Identifier: MIT
"""JK-PB Modbus live block decode (byte-stride doc addresses).

Same map as ../../jk-pb-modbus-read.py — one FC03 from 0x1200.
"""

LIVE_START = 0x1200
LIVE_END = 0x12C2
LIVE_WORDS = (LIVE_END - LIVE_START) // 2 + 1  # 98


def u16(regs, i):
    return regs[i] & 0xFFFF


def s16(regs, i):
    v = regs[i] & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def u32(regs, i):
    return ((regs[i] & 0xFFFF) << 16) | (regs[i + 1] & 0xFFFF)


def s32(regs, i):
    v = u32(regs, i)
    return v - 0x100000000 if v & 0x80000000 else v


def idx(doc_addr, base=LIVE_START):
    return (doc_addr - base) // 2


def decode_live(regs, cells=8):
    """Decode holding registers from LIVE_START into a flat dict for MQTT."""
    i = idx
    cell_v = [u16(regs, n) * 0.001 for n in range(cells)]
    avg_v = u16(regs, i(0x1244)) * 0.001
    dmax_v = u16(regs, i(0x1246)) * 0.001
    mos_c = s16(regs, i(0x128A)) * 0.1
    pack_v = u32(regs, i(0x1290)) * 0.001
    power_w = s32(regs, i(0x1294)) * 0.001
    current_a = s32(regs, i(0x1298)) * 0.001
    t1 = s16(regs, i(0x129C)) * 0.1
    t2 = s16(regs, i(0x129E)) * 0.1
    alarm = u32(regs, i(0x12A0))
    bal_a = s16(regs, i(0x12A4)) * 0.001
    soc_word = u16(regs, i(0x12A6))
    soc = soc_word & 0xFF
    rem_ah = s32(regs, i(0x12A8)) * 0.001
    full_ah = u32(regs, i(0x12AC)) * 0.001
    cycles = u32(regs, i(0x12B0))
    soh = u16(regs, i(0x12B8)) & 0xFF
    runtime_s = u32(regs, i(0x12BC))

    out = {
        "pack/voltage": pack_v,
        "pack/current": current_a,
        "pack/power": power_w,
        "pack/soc": soc,
        "pack/balance_current": bal_a,
        "pack/remain_ah": rem_ah,
        "pack/full_ah": full_ah,
        "pack/cycles": cycles,
        "pack/soh": soh,
        "pack/alarm": alarm,
        "pack/runtime_s": runtime_s,
        "cells/average": avg_v,
        "cells/delta_max": dmax_v,
        "temp/mos": mos_c,
        "temp/battery1": t1,
        "temp/battery2": t2,
    }
    for n in range(cells):
        out["cells/%d" % (n + 1)] = cell_v[n]
    return out


def read_live(modbus, slave, cells=8):
    """FC03 live block → decoded topic map."""
    regs = modbus.read_holding_registers(slave, LIVE_START, LIVE_WORDS)
    return decode_live(regs, cells)
