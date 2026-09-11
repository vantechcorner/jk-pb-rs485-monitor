#!/usr/bin/env python3
"""Modbus RTU master: READ a JK-PB* BMS on RS485-1 (UART1).

Protocol: JK BMS RS485 Modbus V1.0 (app UART1 = 001)
Defaults: slave 15, 115200 8N1. This script never writes.

Example:
  python jk-pb-modbus-read.py --port COM35 --cells 8
  python jk-pb-modbus-read.py --port COM35 --cells 8 --once --full
"""

from __future__ import annotations

import argparse
import sys
import time

from jk_pb_modbus import (
    CFG_WORDS,
    EXTRA_START,
    EXTRA_WORDS,
    INFO_WORDS,
    LIVE_END,
    LIVE_START,
    LIVE_WORDS,
    REG_CFG,
    REG_INFO,
    decode_info,
    decode_live,
    decode_settings,
    make_client,
    merge_extras,
    print_info,
    print_live,
    print_settings,
    read_holding,
    read_holding_span,
)


def poll_once(
    client,
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
        try:
            cfg_regs = read_holding_span(client, REG_CFG, CFG_WORDS, device_id)
            print_settings(decode_settings(cfg_regs))
        except Exception as exc:
            print(f"ERROR: settings 0x1000: {exc}")

        info_regs = None
        last_exc: Exception | None = None
        for nwords in (INFO_WORDS, 64, 56):
            try:
                info_regs = read_holding(client, REG_INFO, nwords, device_id)
                break
            except Exception as exc:
                last_exc = exc
        if info_regs is None:
            print(f"ERROR: device info 0x1400: {last_exc}")
        else:
            print_info(decode_info(info_regs))


def main() -> int:
    p = argparse.ArgumentParser(
        description="JK-PB Modbus RTU reader (UART1 / RS485-1). Read-only."
    )
    p.add_argument("--port", required=True, help="Serial port, e.g. COM35")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--slave-id", type=int, default=15)
    p.add_argument("--cells", type=int, default=16, help="Active cell count (8–16)")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--once", action="store_true")
    p.add_argument(
        "--full",
        action="store_true",
        help="Also read protection settings (0x1000) + device info (0x1400, incl. PIN/password)",
    )
    p.add_argument("--timeout", type=float, default=1.5)
    p.add_argument("--trace", action="store_true")
    args = p.parse_args()

    client = make_client(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        trace=args.trace,
    )
    if not client.connect():
        print(f"Cannot open {args.port}", file=sys.stderr)
        return 1

    print(
        f"JK-PB READ → {args.port} @ {args.baudrate} 8N1, slave {args.slave_id}, "
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
                print(f"ERROR: {exc}")
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
