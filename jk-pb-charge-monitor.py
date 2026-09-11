#!/usr/bin/env python3
"""Terminal charge monitor for a JK-PB* BMS (RS485 / UART1). Read-only.

Shows pack voltage, charge current, balance current, power, remaining
charge time, and per-cell voltages. Refreshes in place (PowerShell / WT).

  python jk-pb-charge-monitor.py --port COM35 --cells 8
  python jk-pb-charge-monitor.py --port COM35 --cells 8 --interval 1
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time

from jk_pb_modbus import (
    LIVE_START,
    LIVE_WORDS,
    charge_metrics,
    decode_alarms,
    decode_live,
    fmt_duration,
    make_client,
    read_holding,
)

CSI = "\033["
CELL_V_MIN = 2.50
CELL_V_MAX = 3.65
BAR_W = 16


def _setup_console() -> None:
    if sys.platform != "win32":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def _tty() -> bool:
    return sys.stdout.isatty()


def _c(code: str, text: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{CSI}{code}m{text}{CSI}0m"


def _bar(v: float, *, color: bool) -> str:
    span = CELL_V_MAX - CELL_V_MIN
    frac = 0.0 if span <= 0 else (v - CELL_V_MIN) / span
    frac = max(0.0, min(1.0, frac))
    n = int(round(frac * BAR_W))
    fill = "#" * n + "." * (BAR_W - n)
    return _c("32", fill, color)


def _eta(eta_s: float | None, charging: bool, need_ah: float) -> str:
    if not charging:
        return "--"
    if need_ah < 0.05:
        return "full"
    if eta_s is None:
        return "--"
    return fmt_duration(int(eta_s))


def _mode_label(mode: str, color: bool) -> str:
    names = {"SAC": "CHARGE", "XA": "DISCHG", "NGHI": "IDLE  "}
    codes = {"SAC": "32;1", "XA": "33;1", "NGHI": "90"}
    return _c(codes[mode], names[mode], color)


def render(m: dict, *, port: str, interval: float, err: str | None, color: bool) -> str:
    now = dt.datetime.now().strftime("%H:%M:%S")
    lines: list[str] = []
    lines.append(
        f"JK-PB charge monitor   {port}   {interval:g}s   {now}   "
        f"[{_mode_label(m['mode'], color)}]"
    )
    lines.append("-" * 68)
    lines.append(
        f"  Voltage         {m['pack_v']:7.3f} V"
        f"     SOC {m['soc_pct']:3d}%     "
        f"{m['remain_ah']:.2f} / {m['full_ah']:.2f} Ah"
    )
    lines.append(
        f"  Charge current  {m['charge_a']:7.3f} A"
        f"     Pack I    {m['pack_i']:+7.3f} A"
    )
    lines.append(
        f"  Balance         {m['balance_a']:+7.3f} A"
        f"     ({m['balance_st']})"
    )
    eta = _eta(m["eta_s"], m["charging"], m["need_ah"])
    need = f"{m['need_ah']:.2f} Ah" if m["charging"] else "--"
    lines.append(
        f"  Power           {m['power_w']:7.1f} W"
        f"     Time left {eta:<10}  ({need})"
    )
    lines.append("-" * 68)

    cells = m["cells"]
    if cells:
        lines.append(
            f"  Cells  (delta {m['dmax_v']*1000:.0f} mV   "
            f"min #{m['imin']+1} {m['vmin']:.3f} V   "
            f"max #{m['imax']+1} {m['vmax']:.3f} V)"
        )
        for n, v in enumerate(cells, start=1):
            tag = ""
            style = "0"
            if n - 1 == m["imin"] and n - 1 == m["imax"]:
                tag = " min=max"
            elif n - 1 == m["imin"]:
                tag = " min"
                style = "36"
            elif n - 1 == m["imax"]:
                tag = " max"
                style = "33"
            volt = _c(style, f"{v:.3f} V", color and style != "0")
            lines.append(f"   {n:2d}  {volt}  {_bar(v, color=color)}{tag}")
    lines.append("-" * 68)
    alarm = decode_alarms(m["alarm"])
    alarm_s = _c("31;1", alarm, color and m["alarm"] != 0)
    lines.append(
        f"  MOS {m['mos_c']:.1f} C   T1 {m['t1']:.1f} C   T2 {m['t2']:.1f} C"
        f"   alarm {alarm_s}"
    )
    if err:
        lines.append(_c("31;1", f"  ERROR: {err}", color))
    lines.append("  Ctrl+C to quit")
    return "\n".join(lines)


def poll_metrics(client, device_id: int, cells: int) -> dict:
    regs = read_holding(client, LIVE_START, LIVE_WORDS, device_id)
    return charge_metrics(decode_live(regs, cells))


def main() -> int:
    p = argparse.ArgumentParser(
        description="JK-PB terminal charge monitor (UART1 / RS485-1). Read-only."
    )
    p.add_argument("--port", required=True, help="Serial port, e.g. COM35")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--slave-id", type=int, default=15)
    p.add_argument("--cells", type=int, default=8, help="Active cell count (lab 8S)")
    p.add_argument("--interval", type=float, default=1.0, help="Refresh seconds")
    p.add_argument("--timeout", type=float, default=1.5)
    p.add_argument("--once", action="store_true", help="Print one frame and exit")
    p.add_argument("--no-color", action="store_true")
    args = p.parse_args()

    _setup_console()
    color = _tty() and not args.no_color
    live = _tty() and not args.once

    client = make_client(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
    )
    if not client.connect():
        print(f"Cannot open {args.port}", file=sys.stderr)
        return 1

    if live:
        sys.stdout.write(f"{CSI}?25l")
        sys.stdout.flush()

    last: dict | None = None
    err: str | None = None
    try:
        while True:
            try:
                last = poll_metrics(client, args.slave_id, args.cells)
                err = None
            except Exception as exc:
                err = str(exc)
            if last is None:
                frame = (
                    f"JK-PB charge monitor   {args.port}\n"
                    f"  ERROR: {err}\n  Ctrl+C to quit"
                )
            else:
                frame = render(
                    last,
                    port=args.port,
                    interval=args.interval,
                    err=err,
                    color=color,
                )
            if live:
                sys.stdout.write(f"{CSI}H{CSI}J{frame}\n")
            else:
                print(frame)
            sys.stdout.flush()
            if args.once:
                break
            time.sleep(max(0.2, args.interval))
    except KeyboardInterrupt:
        if not live:
            print("\nStopped.")
    finally:
        if live:
            sys.stdout.write(f"{CSI}?25h\n")
            sys.stdout.flush()
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
