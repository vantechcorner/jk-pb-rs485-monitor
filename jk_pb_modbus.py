"""JK-PB Modbus RTU helpers (UART1 protocol 001).

Shared by jk-pb-modbus-read.py (FC03 only), jk-pb-charge-monitor.py, and jk-pb-modbus-write.py (FC16).
JK docs use byte-stride addresses; FC03 returns packed 16-bit words:
  word_index = (doc_addr - start_addr) // 2
JK implements FC03 + FC16 only (no FC06).
"""

from __future__ import annotations

from typing import Sequence

from pymodbus.client import ModbusSerialClient

# --- Documented bases (Jikong RS485 Modbus Universal / PB) ---
REG_CFG = 0x1000  # protection / limits (RW)
REG_CELL0 = 0x1200  # live cells + pack status
REG_INFO = 0x1400  # manufacturer / versions / SN / PIN / setup password
INFO_WORDS = 0x90 // 2  # 72 words, through UserData2; password at byte 0x70
# Through device address at byte offset 0x108 (UINT32).
# This firmware rejects 125-word FC03 on 0x1000 (exception 2); 120 is OK.
CFG_WORDS = (0x108 + 4) // 2  # 134
MODBUS_MAX_WORDS = 120

REG_CHG_LIMIT = 0x102C  # CurBatCOC mA
REG_DSG_LIMIT = 0x1038  # CurBatDcOC mA
REG_BAL_EN = 0x1078  # BalanEN 1=on 0=off
# Through balance switch (byte 0x78).
WRITABLE_WORDS = (0x78 + 4) // 2  # 62

CHG_A_MIN, CHG_A_MAX = 0.5, 100.0
DSG_A_MIN, DSG_A_MAX = 1.0, 100.0

LIVE_START = REG_CELL0
LIVE_END = 0x12C2
LIVE_WORDS = (LIVE_END - LIVE_START) // 2 + 1  # 98 words
EXTRA_START = 0x12E6
EXTRA_WORDS = (0x12FC - EXTRA_START) // 2 + 1

ALARM_BITS = [
    (0, "wire_R"),
    (1, "mos_OTP"),
    (2, "cell_qty"),
    (3, "cur_sensor"),
    (4, "cell_OVP"),
    (5, "bat_OVP"),
    (6, "chg_OCP"),
    (7, "chg_SCP"),
    (8, "chg_OTP"),
    (9, "chg_UTP"),
    (10, "cpu_aux"),
    (11, "cell_UVP"),
    (12, "bat_UVP"),
    (13, "dsg_OCP"),
    (14, "dsg_SCP"),
    (15, "dsg_OTP"),
    (16, "chg_MOS"),
    (17, "dsg_MOS"),
    (18, "gps"),
    (19, "pwd"),
    (20, "dsg_start"),
    (21, "bat_OT_alarm"),
]


def u16(regs: Sequence[int], i: int) -> int:
    return regs[i] & 0xFFFF


def s16(regs: Sequence[int], i: int) -> int:
    v = regs[i] & 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def u32(regs: Sequence[int], i: int) -> int:
    return ((regs[i] & 0xFFFF) << 16) | (regs[i + 1] & 0xFFFF)


def s32(regs: Sequence[int], i: int) -> int:
    v = u32(regs, i)
    return v - 0x100000000 if v & 0x80000000 else v


def idx(doc_addr: int, base: int = LIVE_START) -> int:
    return (doc_addr - base) // 2


def ascii_from_regs(regs: Sequence[int], start: int, nbytes: int) -> str:
    raw = bytearray()
    words = (nbytes + 1) // 2
    for i in range(words):
        w = regs[start + i] & 0xFFFF
        raw.append((w >> 8) & 0xFF)
        raw.append(w & 0xFF)
    return bytes(raw[:nbytes]).split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()


def fmt_duration(seconds: int) -> str:
    s = max(0, int(seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if d:
        return f"{d}d {h:02d}:{m:02d}:{s:02d}"
    return f"{h:02d}:{m:02d}:{s:02d}"


# JK-PB protocol 001 current: positive = charge, negative = discharge
# (field-verified on JK-PB1A16S10P while a charger was pushing ~11 A).
IDLE_A = 0.05


def charge_metrics(live: dict) -> dict:
    """Pack fields for the terminal charge monitor (display-only)."""
    i = float(live["current_a"])
    charging = i > IDLE_A
    discharging = i < -IDLE_A
    charge_a = i if charging else 0.0
    need_ah = max(0.0, float(live["full_ah"]) - float(live["remain_ah"]))
    if charging and charge_a > 0:
        eta_s = need_ah / charge_a * 3600.0
    else:
        eta_s = None
    if charging:
        mode = "SAC"
        power_w = abs(float(live["power_w"]))
    elif discharging:
        mode = "XA"
        power_w = abs(float(live["power_w"]))
    else:
        mode = "NGHI"
        power_w = 0.0
    cells = list(live.get("cell_v") or [])
    if cells:
        vmin, vmax = min(cells), max(cells)
        imin = cells.index(vmin)
        imax = cells.index(vmax)
        dmax_v = vmax - vmin
    else:
        vmin = vmax = dmax_v = 0.0
        imin = imax = 0
    return {
        "mode": mode,
        "charging": charging,
        "charge_a": charge_a,
        "pack_i": i,
        "balance_a": float(live["balance_a"]),
        "balance_st": live.get("balance_st") or "off",
        "pack_v": float(live["pack_v"]),
        "power_w": power_w,
        "soc_pct": int(live["soc_pct"]),
        "remain_ah": float(live["remain_ah"]),
        "full_ah": float(live["full_ah"]),
        "need_ah": need_ah,
        "eta_s": eta_s,
        "cells": cells,
        "vmin": vmin,
        "vmax": vmax,
        "imin": imin,
        "imax": imax,
        "dmax_v": dmax_v,
        "mos_c": float(live["mos_temp_c"]),
        "t1": float(live["temp1_c"]),
        "t2": float(live["temp2_c"]),
        "alarm": int(live["alarm"]),
    }


def decode_alarms(mask: int) -> str:
    if mask == 0:
        return "none"
    hits = [name for bit, name in ALARM_BITS if mask & (1 << bit)]
    return ",".join(hits) if hits else f"bits=0x{mask:08X}"


def u32_to_words(value: int) -> list[int]:
    v = int(value) & 0xFFFFFFFF
    return [(v >> 16) & 0xFFFF, v & 0xFFFF]


def amps_to_ma(amps: float) -> int:
    return int(round(float(amps) * 1000.0))


def make_client(
    *,
    port: str,
    baudrate: int = 115200,
    timeout: float = 1.5,
    trace: bool = False,
) -> ModbusSerialClient:
    def trace_packet(is_tx: bool, data: bytes) -> bytes:
        if trace:
            print(f"  {'TX' if is_tx else 'RX'} {data.hex(' ')}")
        return data

    return ModbusSerialClient(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
        trace_packet=trace_packet if trace else None,
    )


def read_holding(
    client: ModbusSerialClient, address: int, count: int, device_id: int
) -> list[int]:
    rr = client.read_holding_registers(address, count=count, device_id=device_id)
    if rr.isError():
        raise RuntimeError(f"FC03 @0x{address:04X}×{count} failed: {rr}")
    return list(rr.registers)


def write_holding_u32(
    client: ModbusSerialClient, address: int, value: int, device_id: int
) -> None:
    """FC16 two packed words (JK does not implement FC06)."""
    words = u32_to_words(value)
    wr = client.write_registers(address, values=words, device_id=device_id)
    if wr.isError():
        raise RuntimeError(f"FC16 @0x{address:04X} {words} failed: {wr}")


def read_holding_span(
    client: ModbusSerialClient, address: int, count: int, device_id: int
) -> list[int]:
    """FC03 a JK byte-stride block, chunked to ≤120 words.

    This firmware rejects a 125-word FC03 on 0x1000 (illegal address).
    Each packed word covers two document-address bytes, so the next chunk
    starts at ``address + n * 2``.
    """
    out: list[int] = []
    remaining = count
    addr = address
    while remaining > 0:
        n = min(remaining, MODBUS_MAX_WORDS)
        out.extend(read_holding(client, addr, n, device_id))
        remaining -= n
        addr += n * 2
    return out


def decode_live(regs: Sequence[int], cells: int) -> dict:
    i = idx
    cell_v = [u16(regs, n) * 0.001 for n in range(cells)]
    cell_present = u32(regs, i(0x1240))
    avg_v = u16(regs, i(0x1244)) * 0.001
    dmax_v = u16(regs, i(0x1246)) * 0.001
    maxmin = u16(regs, i(0x1248))
    max_cell = (maxmin >> 8) & 0xFF
    min_cell = maxmin & 0xFF
    wire_mohm = [u16(regs, i(0x124A) + n) * 0.001 for n in range(cells)]

    mos_c = s16(regs, i(0x128A)) * 0.1
    wire_alarm = u32(regs, i(0x128C))
    pack_v = u32(regs, i(0x1290)) * 0.001
    power_w = s32(regs, i(0x1294)) * 0.001
    current_a = s32(regs, i(0x1298)) * 0.001
    t1 = s16(regs, i(0x129C)) * 0.1
    t2 = s16(regs, i(0x129E)) * 0.1
    alarm = u32(regs, i(0x12A0))
    bal_a = s16(regs, i(0x12A4)) * 0.001
    soc_word = u16(regs, i(0x12A6))
    bal_st = (soc_word >> 8) & 0xFF
    soc = soc_word & 0xFF
    rem_ah = s32(regs, i(0x12A8)) * 0.001
    full_ah = u32(regs, i(0x12AC)) * 0.001
    cycles = u32(regs, i(0x12B0))
    cycle_ah = u32(regs, i(0x12B4)) * 0.001
    soh_word = u16(regs, i(0x12B8))
    soh = soh_word & 0xFF
    precharge = (soh_word >> 8) & 0xFF
    runtime_s = u32(regs, i(0x12BC))
    cd = u16(regs, i(0x12C0))
    charge_en = (cd >> 8) & 0xFF
    discharge_en = cd & 0xFF

    bal_name = {0: "off", 1: "charge", 2: "discharge"}.get(bal_st, str(bal_st))

    return {
        "cell_v": cell_v,
        "cell_present": cell_present,
        "avg_v": avg_v,
        "dmax_v": dmax_v,
        "max_cell": max_cell,
        "min_cell": min_cell,
        "wire_mohm": wire_mohm,
        "wire_alarm": wire_alarm,
        "mos_temp_c": mos_c,
        "pack_v": pack_v,
        "power_w": power_w,
        "current_a": current_a,
        "temp1_c": t1,
        "temp2_c": t2,
        "temp3_c": None,
        "temp4_c": None,
        "temp5_c": None,
        "alarm": alarm,
        "balance_a": bal_a,
        "balance_st": bal_name,
        "soc_pct": soc,
        "remain_ah": rem_ah,
        "full_ah": full_ah,
        "cycles": cycles,
        "cycle_ah": cycle_ah,
        "soh_pct": soh,
        "precharge": precharge,
        "runtime_s": runtime_s,
        "charge_en": charge_en,
        "discharge_en": discharge_en,
        "heat_a": 0.0,
        "charger": None,
    }


def merge_extras(live: dict, regs: Sequence[int]) -> None:
    """Decode optional block starting at EXTRA_START (0x12E6)."""
    base = EXTRA_START

    def j(doc: int) -> int:
        return (doc - base) // 2

    try:
        live["heat_a"] = s16(regs, j(0x12E6)) * 0.001
        live["charger"] = u16(regs, j(0x12EE)) & 0xFF
        live["temp3_c"] = s16(regs, j(0x12F8)) * 0.1
        live["temp4_c"] = s16(regs, j(0x12FA)) * 0.1
        live["temp5_c"] = s16(regs, j(0x12FC)) * 0.1
    except IndexError:
        pass


def decode_settings(regs: Sequence[int]) -> dict:
    """Protection block at 0x1000 — UINT32 values, word index = byte_off // 2."""

    def f32(byte_off: int, scale: float = 0.001) -> float:
        return u32(regs, byte_off // 2) * scale

    def i32(byte_off: int, scale: float = 0.1) -> float:
        return s32(regs, byte_off // 2) * scale

    def raw32(byte_off: int) -> int:
        i = byte_off // 2
        if i + 1 >= len(regs):
            return -1
        return u32(regs, i)

    return {
        "cell_uv_v": f32(0x04),
        "cell_uv_rec_v": f32(0x08),
        "cell_ov_v": f32(0x0C),
        "cell_ov_rec_v": f32(0x10),
        "bal_trig_v": f32(0x14),
        "soc100_v": f32(0x18),
        "soc0_v": f32(0x1C),
        "req_chg_v": f32(0x20),
        "float_v": f32(0x24),
        "pwr_off_v": f32(0x28),
        "chg_limit_a": f32(0x2C),
        "dsg_limit_a": f32(0x38),
        "bal_max_a": f32(0x48),
        "chg_ot_c": i32(0x4C),
        "dsg_ot_c": i32(0x54),
        "chg_ut_c": i32(0x5C),
        "mos_ot_c": i32(0x64),
        "cell_count": raw32(0x6C),
        "chg_sw": raw32(0x70),
        "dsg_sw": raw32(0x74),
        "bal_sw": raw32(0x78),
        "design_ah": f32(0x7C),
        "bal_start_v": f32(0x84),
        "dev_addr": raw32(0x108),
    }


def decode_info(regs: Sequence[int]) -> dict:
    def field(word: int, nbytes: int) -> str:
        need = word + (nbytes + 1) // 2
        if len(regs) < need:
            return ""
        return ascii_from_regs(regs, word, nbytes)

    return {
        "model": field(0, 16),
        "hw": field(8, 8),
        "sw": field(12, 8),
        "run_s": u32(regs, 16) if len(regs) > 17 else 0,
        "power_ons": u32(regs, 18) if len(regs) > 19 else 0,
        "ble": field(20, 16),
        "ble_pin": field(28, 16),  # 0x1438 — Bluetooth login PIN
        "first_on": field(36, 8),
        "sn": field(40, 16),
        "user_data": field(48, 16),
        "password": field(56, 16),  # 0x1470 — Authorize Settings PIN
        "user_data2": field(64, 16),
    }


def read_writable_settings(client: ModbusSerialClient, device_id: int) -> dict:
    """Charge/discharge limits + balance switch (no password)."""
    regs = read_holding(client, REG_CFG, WRITABLE_WORDS, device_id)
    return {
        "chg_limit_a": u32(regs, 0x2C // 2) * 0.001,
        "dsg_limit_a": u32(regs, 0x38 // 2) * 0.001,
        "bal_sw": u32(regs, 0x78 // 2),
    }


def print_live(live: dict, *, dump_hex: bool, regs: Sequence[int] | None) -> None:
    if dump_hex and regs is not None:
        print("live regs:", " ".join(f"{r:04X}" for r in regs[:48]), "...")

    print(
        f"Pack {live['pack_v']:.3f} V | {live['current_a']:+.3f} A | "
        f"{live['power_w']:+.1f} W | SOC {live['soc_pct']}% | SOH {live['soh_pct']}%"
    )
    print(
        f"Temp MOS {live['mos_temp_c']:.1f} °C | T1 {live['temp1_c']:.1f} °C | "
        f"T2 {live['temp2_c']:.1f} °C | bal {live['balance_a']:+.3f} A ({live['balance_st']})"
    )
    extras = []
    for label, key in (("T3", "temp3_c"), ("T4", "temp4_c"), ("T5", "temp5_c")):
        v = live.get(key)
        if v is not None and abs(v) < 200:
            extras.append(f"{label} {v:.1f}")
    if extras:
        print("       " + " | ".join(extras) + " °C")

    print(
        f"Ah {live['remain_ah']:.2f}/{live['full_ah']:.2f} | "
        f"cycle_cap {live['cycle_ah']:.1f} Ah | cycles {live['cycles']} | "
        f"runtime {fmt_duration(live['runtime_s'])}"
    )
    print(
        f"MOS chg={live['charge_en']} dsg={live['discharge_en']} | "
        f"precharge={live['precharge']} | heat {live['heat_a']:+.3f} A | "
        f"charger={live['charger']}"
    )
    print(
        f"Alarm 0x{live['alarm']:08X} ({decode_alarms(live['alarm'])}) | "
        f"wire_alarm 0x{live['wire_alarm']:08X}"
    )

    cell_v = live["cell_v"]
    if cell_v:
        delta_mv = (max(cell_v) - min(cell_v)) * 1000
        shown = " ".join(f"{v:.3f}" for v in cell_v)
        present = bin(live["cell_present"] & ((1 << len(cell_v)) - 1))
        print(
            f"Cells[{len(cell_v)}] avg {live['avg_v']:.3f} V | "
            f"Δmax {live['dmax_v']*1000:.0f} mV (meas Δ{delta_mv:.0f}) | "
            f"max#{live['max_cell']} min#{live['min_cell']} | present {present}"
        )
        print(f"  V: {shown}")
        wires = " ".join(f"{r:.3f}" for r in live["wire_mohm"])
        print(f"  R_wire Ω: {wires}")
    print("-" * 60)


def print_settings(cfg: dict) -> None:
    print("=== Settings / protection (0x1000) ===")
    print(
        f"Cells set={cfg['cell_count']} | design {cfg['design_ah']:.1f} Ah | "
        f"dev_addr={cfg['dev_addr'] if cfg['dev_addr'] >= 0 else '?'} | "
        f"sw chg={cfg['chg_sw']} dsg={cfg['dsg_sw']} bal={cfg['bal_sw']}"
    )
    print(
        f"Cell UV {cfg['cell_uv_v']:.3f}/{cfg['cell_uv_rec_v']:.3f} V | "
        f"OV {cfg['cell_ov_v']:.3f}/{cfg['cell_ov_rec_v']:.3f} V"
    )
    print(
        f"SOC cal 100%@{cfg['soc100_v']:.3f} V  0%@{cfg['soc0_v']:.3f} V | "
        f"bal trig Δ{cfg['bal_trig_v']*1000:.0f} mV start@{cfg['bal_start_v']:.3f} V "
        f"max {cfg['bal_max_a']:.2f} A"
    )
    print(
        f"Limits chg {cfg['chg_limit_a']:.1f} A / dsg {cfg['dsg_limit_a']:.1f} A | "
        f"req_chg {cfg['req_chg_v']:.3f} V float {cfg['float_v']:.3f} V "
        f"pwr_off {cfg['pwr_off_v']:.3f} V"
    )
    print(
        f"Temp chg OT {cfg['chg_ot_c']:.1f} / UT {cfg['chg_ut_c']:.1f} °C | "
        f"dsg OT {cfg['dsg_ot_c']:.1f} °C | MOS OT {cfg['mos_ot_c']:.1f} °C"
    )
    print("-" * 60)


def print_info(info: dict) -> None:
    print("=== Device info (0x1400) ===")
    print(f"Model {info['model']!r} | HW {info['hw']!r} | SW {info['sw']!r}")
    print(
        f"SN {info['sn']!r} | BLE {info['ble']!r} | "
        f"power_ons {info['power_ons']} | odd_run {fmt_duration(info['run_s'])}"
    )
    extra = []
    if info.get("first_on"):
        extra.append(f"first_on {info['first_on']!r}")
    if info.get("user_data"):
        extra.append(f"user {info['user_data']!r}")
    if extra:
        print("       " + " | ".join(extra))
    print(
        f"BLE PIN {info.get('ble_pin') or '(empty)'} | "
        f"setup password {info.get('password') or '(empty)'}"
    )
    print("-" * 60)


def print_writable(st: dict) -> None:
    bal = "on" if st["bal_sw"] else "off"
    print(
        f"Writable: chg {st['chg_limit_a']:.1f} A | "
        f"dsg {st['dsg_limit_a']:.1f} A | balance {bal}"
    )
