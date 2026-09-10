#!/usr/bin/env python3
"""JK-PB Modbus RTU slave emulator (USB-RS485) — UART1 protocol 001 live map.

Bench stand-in for a real JK-PB* BMS so you can test PC poller / IRIV firmware
without hardware. Defaults: slave **15**, **115200** 8N1, FC03 from **0x1200**.

Examples:
  python emulator/jk-pb-emu.py --port COM36 --debug --cells 8 --scenario day
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rs485_emu.core.cli import add_common_args, setup_logging
from rs485_emu.core.server import run_serial_emulator
from rs485_emu.core.tracer import FrameTracer
from rs485_emu.profiles.bms_jk import LIVE_START, LIVE_WORDS, JkPbSimulator, create_bank


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "JK-PB Modbus RTU slave emulator (live block 0x1200). "
            "Matches jk-pb-modbus-read.py / IRIV CircuitPython firmware."
        )
    )
    add_common_args(parser)
    parser.set_defaults(baudrate=115200, slave_id=15)
    parser.add_argument(
        "--cells",
        type=int,
        default=8,
        choices=(4, 8, 16),
        help="Simulated series count (default: 8)",
    )
    args = parser.parse_args(argv)
    setup_logging(debug=args.debug, trace=args.trace)

    bank = create_bank()
    sim = JkPbSimulator(
        bank, cells=args.cells, scenario=args.scenario, seed=args.seed
    )
    tracer = FrameTracer(
        debug=args.debug,
        trace=args.trace,
        bank=bank,
        meta_by_addr={},
        known_addresses=set(range(LIVE_START, LIVE_START + LIVE_WORDS)),
    )

    asyncio.run(
        run_serial_emulator(
            title="JK-PB BMS emulator (Modbus RTU / protocol 001)",
            bank=bank,
            slave_id=args.slave_id,
            port=args.port,
            baudrate=args.baudrate,
            tracer=tracer,
            tick=sim.tick,
            tick_interval=args.tick,
            extra_banner={
                "Scenario": args.scenario,
                "Cells": args.cells,
                "Live map": f"FC03 0x{LIVE_START:04X} × {LIVE_WORDS} words",
            },
        )
    )


if __name__ == "__main__":
    main()
