#!/usr/bin/env python3
"""Modbus RTU master: WRITE basic JK-PB* settings on RS485-1 (UART1).

Charge current, discharge current, balance switch. FC16 only.
Never writes OVP/UVP/MOS/password. Dry-run unless --yes.

Example:
  python jk-pb-modbus-write.py --port COM35
  python jk-pb-modbus-write.py --port COM35 --set-charge-a 10 --balance on
  python jk-pb-modbus-write.py --port COM35 --set-charge-a 10 --yes
"""

from __future__ import annotations

import argparse
import sys
import time

from jk_pb_modbus import (
    CHG_A_MAX,
    CHG_A_MIN,
    DSG_A_MAX,
    DSG_A_MIN,
    REG_BAL_EN,
    REG_CHG_LIMIT,
    REG_DSG_LIMIT,
    amps_to_ma,
    make_client,
    print_writable,
    read_writable_settings,
    u32_to_words,
    write_holding_u32,
)


def _on_off(value: str) -> int:
    v = value.strip().lower()
    if v in ("on", "1", "true", "yes"):
        return 1
    if v in ("off", "0", "false", "no"):
        return 0
    raise argparse.ArgumentTypeError("use on or off")


def _check_amps(name: str, amps: float, lo: float, hi: float) -> float:
    if amps != amps:  # NaN
        raise ValueError(f"{name} is not a number")
    if amps < lo or amps > hi:
        raise ValueError(f"{name} {amps:g} A is outside {lo:g}–{hi:g} A")
    return float(amps)


def apply_settings(
    client,
    device_id: int,
    *,
    charge_a: float | None,
    discharge_a: float | None,
    balance: int | None,
    commit: bool,
) -> int:
    if charge_a is not None:
        charge_a = _check_amps("charge", charge_a, CHG_A_MIN, CHG_A_MAX)
    if discharge_a is not None:
        discharge_a = _check_amps("discharge", discharge_a, DSG_A_MIN, DSG_A_MAX)

    before = read_writable_settings(client, device_id)
    print("Before:")
    print_writable(before)

    jobs: list[tuple[str, int, int, int, str]] = []
    if charge_a is not None:
        jobs.append(
            (
                "charge",
                REG_CHG_LIMIT,
                amps_to_ma(charge_a),
                amps_to_ma(before["chg_limit_a"]),
                f"{before['chg_limit_a']:.1f} A → {charge_a:.1f} A",
            )
        )
    if discharge_a is not None:
        jobs.append(
            (
                "discharge",
                REG_DSG_LIMIT,
                amps_to_ma(discharge_a),
                amps_to_ma(before["dsg_limit_a"]),
                f"{before['dsg_limit_a']:.1f} A → {discharge_a:.1f} A",
            )
        )
    if balance is not None:
        old_b = 1 if before["bal_sw"] else 0
        jobs.append(
            (
                "balance",
                REG_BAL_EN,
                balance,
                old_b,
                f"{'on' if old_b else 'off'} → {'on' if balance else 'off'}",
            )
        )

    if not jobs:
        return 0

    action = "WRITE" if commit else "DRY-RUN"
    for name, addr, new_v, _old_v, label in jobs:
        words = u32_to_words(new_v)
        print(
            f"  {action} {name}: {label}  "
            f"FC16 @0x{addr:04X} {words[0]:04X} {words[1]:04X}"
        )

    if not commit:
        print("No write sent. Re-run with --yes to commit.")
        return 0

    for name, addr, new_v, old_v, _label in jobs:
        if new_v == old_v:
            print(f"  skip {name}: already {new_v}")
            continue
        write_holding_u32(client, addr, new_v, device_id)
        print(f"  wrote {name}")

    time.sleep(0.4)
    after = read_writable_settings(client, device_id)
    print("After:")
    print_writable(after)

    ok = True
    if charge_a is not None and abs(after["chg_limit_a"] - charge_a) > 0.05:
        print(f"ERROR: charge read-back {after['chg_limit_a']:.1f} A ≠ {charge_a:.1f} A")
        ok = False
    if discharge_a is not None and abs(after["dsg_limit_a"] - discharge_a) > 0.05:
        print(f"ERROR: discharge read-back {after['dsg_limit_a']:.1f} A ≠ {discharge_a:.1f} A")
        ok = False
    if balance is not None:
        got = 1 if after["bal_sw"] else 0
        if got != balance:
            print(f"ERROR: balance read-back {got} ≠ {balance}")
            ok = False
    if not ok:
        return 1
    print("OK.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "JK-PB Modbus RTU writer (UART1 / RS485-1). "
            "Charge/discharge current and balance switch only."
        )
    )
    p.add_argument("--port", required=True, help="Serial port, e.g. COM35")
    p.add_argument("--baudrate", type=int, default=115200)
    p.add_argument("--slave-id", type=int, default=15)
    p.add_argument("--timeout", type=float, default=1.5)
    p.add_argument("--trace", action="store_true")
    p.add_argument(
        "--set-charge-a",
        type=float,
        metavar="A",
        help=f"Continuous charge current CurBatCOC ({CHG_A_MIN:g}–{CHG_A_MAX:g} A)",
    )
    p.add_argument(
        "--set-discharge-a",
        type=float,
        metavar="A",
        help=f"Continuous discharge current CurBatDcOC ({DSG_A_MIN:g}–{DSG_A_MAX:g} A)",
    )
    p.add_argument(
        "--balance",
        type=_on_off,
        metavar="on|off",
        help="Balance switch BalanEN (on/off)",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Commit the write (otherwise dry-run / show current values)",
    )
    args = p.parse_args()

    setting = (
        args.set_charge_a is not None
        or args.set_discharge_a is not None
        or args.balance is not None
    )
    if args.yes and not setting:
        print("ERROR: --yes requires --set-charge-a, --set-discharge-a, and/or --balance")
        return 2

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
        f"JK-PB WRITE → {args.port} @ {args.baudrate} 8N1, slave {args.slave_id}"
        + ("  FC16" if setting else "  (show only)")
    )
    rc = 0
    try:
        try:
            if setting:
                rc = apply_settings(
                    client,
                    args.slave_id,
                    charge_a=args.set_charge_a,
                    discharge_a=args.set_discharge_a,
                    balance=args.balance,
                    commit=args.yes,
                )
            else:
                print_writable(read_writable_settings(client, args.slave_id))
        except Exception as exc:
            print(f"ERROR: {exc}")
            rc = 1
    finally:
        client.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
