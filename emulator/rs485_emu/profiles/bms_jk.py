"""JK-PB RS485 Modbus V1.0 live map (UART1 protocol 001) — bench slave.

Serves the same FC03 live window as `jk-pb-modbus-read.py` /
`iriv-ioc/firmware/lib/jk_bms.py`: start **0x1200**, 98 words.

JK docs use byte-stride addresses (0x1200, 0x1202, …). On the wire the master
reads consecutive Modbus registers from 0x1200; word index =
`(doc_addr - 0x1200) // 2`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from rs485_emu.core.registers import RegisterBank

LIVE_START = 0x1200
LIVE_END = 0x12C2
LIVE_WORDS = (LIVE_END - LIVE_START) // 2 + 1  # 98


def _mb(doc_addr: int) -> int:
    """Document byte address → consecutive Modbus register address."""
    return LIVE_START + (doc_addr - LIVE_START) // 2


@dataclass
class JkSimState:
    scenario: str = "day"
    cells: int = 8
    soc: float = 67.0
    soh: float = 100.0
    current_a: float = 0.5  # + charge, − discharge (JK-PB protocol 001, field-verified)
    temp_mos: float = 32.0
    temp1: float = 28.5
    temp2: float = 28.0
    remain_ah: float = 33.5
    full_ah: float = 50.0
    cycles: int = 12
    runtime_s: int = 3600
    rng: random.Random = field(default_factory=random.Random)


class JkPbSimulator:
    def __init__(
        self,
        bank: RegisterBank,
        *,
        cells: int = 8,
        scenario: str = "day",
        seed: int | None = None,
    ):
        self.bank = bank
        self.state = JkSimState(scenario=scenario, cells=max(4, min(16, cells)))
        if seed is not None:
            self.state.rng.seed(seed)
        self._paint()

    def _cell_voltages(self) -> list[float]:
        st = self.state
        # ~3.32 V/cell nominal for mid-SOC LFP; slight imbalance
        base = 3.20 + (st.soc / 100.0) * 0.25
        vs = []
        for i in range(st.cells):
            noise = st.rng.uniform(-0.003, 0.003)
            vs.append(max(2.8, min(3.55, base + (i % 3) * 0.001 + noise)))
        return vs

    def _paint(self) -> None:
        st = self.state
        b = self.bank
        cells = self._cell_voltages()
        # Pad unused cell slots to 16 words with 0
        for n in range(16):
            mv = int(round(cells[n] * 1000)) if n < len(cells) else 0
            b.write_u16(_mb(0x1200 + 2 * n), mv)

        avg = sum(cells) / len(cells)
        dmax = max(cells) - min(cells)
        pack_v = sum(cells)
        power_w = pack_v * st.current_a

        b.write_u16(_mb(0x1244), int(round(avg * 1000)))
        b.write_u16(_mb(0x1246), int(round(dmax * 1000)))
        # max/min cell index packed (1-based)
        imax = cells.index(max(cells)) + 1
        imin = cells.index(min(cells)) + 1
        b.write_u16(_mb(0x1248), ((imax & 0xFF) << 8) | (imin & 0xFF))

        b.write_s16(_mb(0x128A), int(round(st.temp_mos * 10)))
        b.write_u32_be(_mb(0x1290), int(round(pack_v * 1000)))
        b.write_s32_be(_mb(0x1294), int(round(power_w * 1000)))
        b.write_s32_be(_mb(0x1298), int(round(st.current_a * 1000)))
        b.write_s16(_mb(0x129C), int(round(st.temp1 * 10)))
        b.write_s16(_mb(0x129E), int(round(st.temp2 * 10)))
        b.write_u32_be(_mb(0x12A0), 0 if st.scenario != "fault" else 0x800)
        b.write_s16(_mb(0x12A4), 0)  # balance current
        # SOC low byte, balance state high byte
        b.write_u16(_mb(0x12A6), int(round(st.soc)) & 0xFF)
        b.write_s32_be(_mb(0x12A8), int(round(st.remain_ah * 1000)))
        b.write_u32_be(_mb(0x12AC), int(round(st.full_ah * 1000)))
        b.write_u32_be(_mb(0x12B0), st.cycles)
        b.write_u16(_mb(0x12B8), int(round(st.soh)) & 0xFF)
        b.write_u32_be(_mb(0x12BC), st.runtime_s & 0xFFFFFFFF)
        b.write_u16(_mb(0x12C0), 0x0101)  # charge/discharge enable bytes

    def tick(self, dt: float) -> None:
        st = self.state
        if st.scenario == "night":
            target_i = st.rng.uniform(1.0, 5.0)  # charge
        elif st.scenario == "cloud":
            target_i = st.rng.uniform(-12.0, 8.0)
        elif st.scenario == "fault":
            target_i = 0.0
        else:
            target_i = st.rng.uniform(-8.0, 3.0)

        st.current_a += (target_i - st.current_a) * min(1.0, dt * 0.4)
        if st.scenario == "fault":
            st.current_a = 0.0

        # Ah accounting: +current = charge
        st.remain_ah += st.current_a * dt / 3600.0
        st.remain_ah = max(1.0, min(st.full_ah, st.remain_ah))
        st.soc = 100.0 * st.remain_ah / st.full_ah
        st.runtime_s = (st.runtime_s + int(dt)) & 0xFFFFFFFF
        st.temp_mos += (30.0 + abs(st.current_a) * 0.15 - st.temp_mos) * 0.05
        st.temp1 += (28.0 + abs(st.current_a) * 0.05 - st.temp1) * 0.03
        st.temp2 += (27.5 + abs(st.current_a) * 0.04 - st.temp2) * 0.03
        self._paint()


def create_bank() -> RegisterBank:
    # Registers 0x1200 … 0x1200+97 (consecutive Modbus addresses for the live block).
    return RegisterBank(size=LIVE_WORDS + 8, base_address=LIVE_START)
