"""Async serial Modbus RTU slave server runner.

Starts pymodbus ModbusSerialServer with SimDevice + optional simulation tick
and FrameTracer (--debug / --trace). Emulator process is always the Modbus
slave; attach ESPHome / IRIV / other masters on the RS485 bus.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import pymodbus
from pymodbus.server import ModbusSerialServer

from .registers import RegisterBank
from .tracer import FrameTracer

LOG = logging.getLogger("rs485_emu.server")


async def run_serial_emulator(
    *,
    title: str,
    bank: RegisterBank,
    slave_id: int,
    port: str,
    baudrate: int,
    tracer: FrameTracer,
    tick: Callable[[float], None] | Callable[[float], Awaitable[None]],
    tick_interval: float = 1.0,
    extra_banner: dict[str, Any] | None = None,
) -> None:
    device = bank.build_sim_device(slave_id)

    LOG.info("=" * 54)
    LOG.info("%s", title)
    LOG.info("Serial : %s @ %d 8N1", port, baudrate)
    LOG.info("Slave  : %s", slave_id)
    LOG.info("Pymodbus: %s", pymodbus.__version__)
    if extra_banner:
        for key, value in extra_banner.items():
            LOG.info("%s: %s", key, value)
    LOG.info("=" * 54)

    server = ModbusSerialServer(
        context=device,
        port=port,
        baudrate=baudrate,
        stopbits=1,
        bytesize=8,
        parity="N",
        timeout=3,
        trace_packet=tracer.trace_packet if tracer.trace else None,
        trace_pdu=tracer.trace_pdu if tracer.trace else None,
    )

    async def _ticker() -> None:
        # Bind live register list ASAP via a no-op sync path after short delay.
        await asyncio.sleep(0.05)
        last = asyncio.get_running_loop().time()
        while True:
            await asyncio.sleep(tick_interval)
            now = asyncio.get_running_loop().time()
            dt = now - last
            last = now
            result = tick(dt)
            if asyncio.iscoroutine(result):
                await result
            bank.sync_to_live()
            if tracer.req_count and tracer.req_count % 20 == 0:
                LOG.info("stats %s", tracer.summary_line())

    tick_task = asyncio.create_task(_ticker(), name="sim-tick")
    try:
        await server.serve_forever()
    finally:
        tick_task.cancel()
        try:
            await tick_task
        except asyncio.CancelledError:
            pass
        await server.shutdown()
