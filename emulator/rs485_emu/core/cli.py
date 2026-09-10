"""Common CLI options for RS485 emulators."""

from __future__ import annotations

import argparse
import logging


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port",
        default="COM35",
        help="Serial port of USB-RS485 adapter (default: COM35)",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=9600,
        help="Baud rate (default: 9600)",
    )
    parser.add_argument(
        "--slave-id",
        type=int,
        default=1,
        help="Modbus slave / device id (default: 1)",
    )
    parser.add_argument(
        "--tick",
        type=float,
        default=1.0,
        help="Simulator tick interval in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--scenario",
        choices=("day", "night", "cloud", "fault"),
        default="day",
        help="Simulation scenario (default: day)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Log each Modbus register access with engineering values",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Dump raw RTU hex frames (RX/TX)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional RNG seed for reproducible noise",
    )


def parse_common(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_common_args(parser)
    return parser.parse_args(argv)


def setup_logging(*, debug: bool, trace: bool) -> None:
    level = logging.DEBUG if (debug or trace) else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy pymodbus internals unless tracing.
    if not trace:
        logging.getLogger("pymodbus").setLevel(logging.WARNING)
