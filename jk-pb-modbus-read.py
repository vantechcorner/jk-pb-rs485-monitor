#!/usr/bin/env python3
"""Modbus RTU master: poll a real JK-PB* BMS on RS485-1 (UART1).

Protocol: JK BMS RS485 Modbus V1.0 (app UART1 = 001)
Defaults: slave 15, 115200 8N1.

JK docs use byte-style addresses (…1200, 1202, 128A, 1290…).
Empirically, FC03 returns packed 16-bit words where
  word_index = (doc_addr - start_addr) // 2.

Example:
  python jk-pb-modbus-read.py --port COM35 --cells 8
  python jk-pb-modbus-read.py --port COM35 --cells 8 --once --full
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Sequence

from pymodbus.client import ModbusSerialClient

# --- Documented bases (Jikong RS485 Modbus Universal / PB) ---
REG_CFG = 0x1000  # protection / limits (RW)
REG_CELL0 = 0x1200  # live cells + pack status
REG_INFO = 0x1400  # manufacturer / versions / SN

# Live window: cells → charge/discharge flags (keep ≤125 Modbus words)
LIVE_START = REG_CELL0
LIVE_END = 0x12C2
LIVE_WORDS = (LIVE_END - LIVE_START) // 2 + 1  # 98 words
EXTRA_START = 0x12E6  # heat current … TempBat5
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


def decode_alarms(mask: int) -> str:
    if mask == 0:
        return "none"
    hits = [name for bit, name in ALARM_BITS if mask & (1 << bit)]
    return ",".join(hits) if hits else f"bits=0x{mask:08X}"


def read_holding(
    client: ModbusSerialClient, address: int, count: int, device_id: int
) -> list[int]:
    rr = client.read_holding_registers(address, count=count, device_id=device_id)
    if rr.isError():
        raise RuntimeError(f"FC03 @0x{address:04X}×{count} failed: {rr}")
    return list(rr.registers)


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
        return u32(regs, byte_off // 2)

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
    return {
        "model": ascii_from_regs(regs, 0, 16),
        "hw": ascii_from_regs(regs, 8, 8),
        "sw": ascii_from_regs(regs, 12, 8),
        "run_s": u32(regs, 16),
        "power_ons": u32(regs, 18),
        "ble": ascii_from_regs(regs, 20, 16),
        "sn": ascii_from_regs(regs, 40, 16),
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
        f"dev_addr={cfg['dev_addr']} | "
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
    print("-" * 60)


def poll_once(
    client: ModbusSerialClient,
    device_id: int,
    cells: int,
    *,
    full: bool,
    dump_hex: bool,
) -> None:
    regs = read_holding(client, LIVE_START, LIVE_WORDS, device_id)
    live = decode_live(regs, cells)
    try:
        merge_extras(live, read_holding(client, EXTRA_START, EXTRA_WORDS, device_id))
    except Exception:
        pass  # older FW / short map — main live still OK
    print_live(live, dump_hex=dump_hex, regs=regs if dump_hex else None)

    if full:
        cfg_regs = read_holding(client, REG_CFG, 140, device_id)
        print_settings(decode_settings(cfg_regs))
        info_regs = read_holding(client, REG_INFO, 56, device_id)
        print_info(decode_info(info_regs))


def main() -> int:
    p = argparse.ArgumentParser(description="JK-PB Modbus RTU reader (UART1 / RS485-1)")
    p.add_argument("--port", required=True, help="Serial port, e.g. COM35")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--slave-id", type=int, default=15)
    p.add_argument("--cells", type=int, default=16, help="Active cell count (8–16)")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--once", action="store_true")
    p.add_argument(
        "--full",
        action="store_true",
        help="Also read protection settings (0x1000) + device info (0x1400)",
    )
    p.add_argument("--timeout", type=float, default=1.5)
    p.add_argument("--trace", action="store_true")
    args = p.parse_args()

    def trace_packet(is_tx: bool, data: bytes) -> bytes:
        if args.trace:
            print(f"  {'TX' if is_tx else 'RX'} {data.hex(' ')}")
        return data

    client = ModbusSerialClient(
        port=args.port,
        baudrate=args.baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=args.timeout,
        trace_packet=trace_packet if args.trace else None,
    )
    if not client.connect():
        print(f"Cannot open {args.port}", file=sys.stderr)
        return 1

    print(
        f"JK-PB master → {args.port} @ {args.baudrate} 8N1, slave {args.slave_id}, "
        f"FC03 0x{LIVE_START:04X}…0x{LIVE_END:04X}"
        + (" +settings+info" if args.full else "")
    )
    try:
        while True:
            try:
                poll_once(
                    client,
                    args.slave_id,
                    args.cells,
                    full=args.full,
                    dump_hex=args.trace,
                )
            except Exception as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
