"""Holding-register bank helpers for pymodbus SimDevice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pymodbus.constants import ExcCodes
from pymodbus.simulator import DataType, SimData, SimDevice


def to_s16(value: int) -> int:
    """Encode a signed integer as Modbus uint16 (two's complement)."""
    return int(value) & 0xFFFF


def from_s16(raw: int) -> int:
    """Decode Modbus uint16 as signed int16."""
    raw = int(raw) & 0xFFFF
    return raw - 0x10000 if raw & 0x8000 else raw


@dataclass(frozen=True)
class RegisterMeta:
    address: int
    name: str
    scale: float = 1.0
    signed: bool = False
    unit: str = ""
    offset: float = 0.0  # engineering = raw * scale + offset  (or custom)

    def encode(self, engineering: float) -> int:
        raw = round((engineering - self.offset) / self.scale) if self.scale else 0
        return to_s16(raw) if self.signed else int(raw) & 0xFFFF

    def decode(self, raw: int) -> float:
        value = from_s16(raw) if self.signed else (raw & 0xFFFF)
        return value * self.scale + self.offset


class RegisterBank:
    """Mutable holding-register image bound to a live SimRuntime list on first access."""

    def __init__(self, size: int = 1024, *, base_address: int = 0):
        self.base_address = base_address
        self.size = size
        self.values = [0] * size
        self._live: list[int] | None = None
        self._live_start = 0
        self._on_access: Callable[..., None] | None = None

    def set_access_hook(self, hook: Callable[..., None] | None) -> None:
        self._on_access = hook

    def write(self, address: int, raw: int) -> None:
        idx = address - self.base_address
        if not 0 <= idx < self.size:
            return
        raw = int(raw) & 0xFFFF
        self.values[idx] = raw
        if self._live is not None:
            live_idx = address - self._live_start
            if 0 <= live_idx < len(self._live):
                self._live[live_idx] = raw

    def write_u16(self, address: int, value: int) -> None:
        self.write(address, int(value) & 0xFFFF)

    def write_s16(self, address: int, value: int) -> None:
        self.write(address, to_s16(value))

    def write_u32_le(self, address: int, value: int) -> None:
        """Low word at address, high word at address+1 (Deye U_DWORD_R style)."""
        value = int(value) & 0xFFFFFFFF
        self.write_u16(address, value & 0xFFFF)
        self.write_u16(address + 1, (value >> 16) & 0xFFFF)

    def write_u32_be(self, address: int, value: int) -> None:
        """High word at address, low word at address+1 (JK u32/s32 ABCD)."""
        value = int(value) & 0xFFFFFFFF
        self.write_u16(address, (value >> 16) & 0xFFFF)
        self.write_u16(address + 1, value & 0xFFFF)

    def write_s32_be(self, address: int, value: int) -> None:
        self.write_u32_be(address, int(value) & 0xFFFFFFFF)

    def read(self, address: int) -> int:
        idx = address - self.base_address
        if not 0 <= idx < self.size:
            return 0
        return self.values[idx]

    def apply_meta(self, meta: RegisterMeta, engineering: float) -> None:
        self.write(meta.address, meta.encode(engineering))

    def sync_to_live(self) -> None:
        if self._live is None:
            return
        for addr_offset, raw in enumerate(self.values):
            address = self.base_address + addr_offset
            live_idx = address - self._live_start
            if 0 <= live_idx < len(self._live):
                self._live[live_idx] = raw

    async def action(
        self,
        function_code: int,
        start_address: int,
        address: int,
        count: int,
        current_registers: list[int],
        set_values: list[int] | list[bool] | None,
    ) -> ExcCodes | None:
        if self._live is None:
            self._live = current_registers
            self._live_start = start_address
            self.sync_to_live()

        if set_values is None:
            # Ensure reads see latest simulated values.
            for i in range(count):
                a = address + i
                idx = a - self.base_address
                live_idx = a - start_address
                if 0 <= idx < self.size and 0 <= live_idx < len(current_registers):
                    current_registers[live_idx] = self.values[idx]

        if self._on_access:
            self._on_access(
                function_code, address, count, current_registers, set_values
            )
        return None

    def build_sim_device(self, slave_id: int) -> SimDevice:
        return SimDevice(
            id=slave_id,
            simdata=[
                SimData(
                    self.base_address,
                    values=list(self.values),
                    datatype=DataType.REGISTERS,
                )
            ],
            action=self.action,
        )
