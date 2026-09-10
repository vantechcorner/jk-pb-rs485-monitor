"""Request/response tracing for Modbus RTU frames."""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import TYPE_CHECKING

from pymodbus.pdu import ModbusPDU

if TYPE_CHECKING:
    from .registers import RegisterBank, RegisterMeta

LOG = logging.getLogger("rs485_emu.trace")

FC_NAMES = {
    0x01: "ReadCoils",
    0x02: "ReadDiscrete",
    0x03: "ReadHolding",
    0x04: "ReadInput",
    0x05: "WriteCoil",
    0x06: "WriteSingle",
    0x0F: "WriteCoils",
    0x10: "WriteMultiple",
}


def _hex(data: bytes) -> str:
    return data.hex(" ")


class FrameTracer:
    def __init__(
        self,
        *,
        debug: bool = False,
        trace: bool = False,
        bank: RegisterBank | None = None,
        meta_by_addr: dict[int, RegisterMeta] | None = None,
        known_addresses: set[int] | None = None,
    ):
        self.debug = debug
        self.trace = trace
        self.bank = bank
        self.meta_by_addr = meta_by_addr or {}
        self.known_addresses = known_addresses or set(self.meta_by_addr)
        self.req_count = 0
        self.by_fc: Counter[int] = Counter()
        self.unknown_addrs: Counter[int] = Counter()
        self.last_req_ts = 0.0
        self._started = time.monotonic()

        if bank is not None:
            bank.set_access_hook(self.on_register_access)

    def on_register_access(
        self,
        function_code: int,
        address: int,
        count: int,
        current_registers: list[int],
        set_values: list[int] | list[bool] | None,
    ) -> None:
        self.req_count += 1
        self.by_fc[function_code] += 1
        self.last_req_ts = time.monotonic()
        op = "WR" if set_values is not None else "RD"
        fc_name = FC_NAMES.get(function_code, f"FC{function_code:02X}")

        decoded = []
        for i in range(count):
            addr = address + i
            if self.known_addresses and addr not in self.known_addresses:
                self.unknown_addrs[addr] += 1
            meta = self.meta_by_addr.get(addr)
            if meta and self.bank is not None:
                eng = meta.decode(self.bank.read(addr))
                decoded.append(f"{meta.name}={eng:.2f}{meta.unit}")
            elif self.debug:
                decoded.append(f"[{addr}]=?")

        if self.debug or self.trace:
            extra = (" | " + ", ".join(decoded[:8])) if decoded else ""
            more = f" (+{len(decoded) - 8} more)" if len(decoded) > 8 else ""
            LOG.info(
                "%s %s addr=%s qty=%s%s%s",
                op,
                fc_name,
                address,
                count,
                extra,
                more,
            )

    def trace_packet(self, is_receiving: bool, data: bytes) -> bytes:
        if self.trace and data:
            direction = "RX" if is_receiving else "TX"
            LOG.info("%s (%d B): %s", direction, len(data), _hex(data))
        return data

    def trace_pdu(self, is_receiving: bool, pdu: ModbusPDU) -> ModbusPDU:
        if self.trace:
            direction = "RX-PDU" if is_receiving else "TX-PDU"
            LOG.info(
                "%s dev=%s fc=%s",
                direction,
                getattr(pdu, "dev_id", "?"),
                getattr(pdu, "function_code", "?"),
            )
        return pdu

    def summary_line(self) -> str:
        idle = (
            time.monotonic() - self.last_req_ts
            if self.last_req_ts
            else time.monotonic() - self._started
        )
        unknown = ""
        if self.unknown_addrs:
            top = ", ".join(
                f"{a}×{c}" for a, c in self.unknown_addrs.most_common(5)
            )
            unknown = f" | unknown_addrs=[{top}]"
        return (
            f"reqs={self.req_count} fc={dict(self.by_fc)} "
            f"idle={idle:.1f}s{unknown}"
        )
