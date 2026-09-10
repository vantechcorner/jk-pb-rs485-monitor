# SPDX-License-Identifier: MIT
"""Minimal Modbus RTU master (FC03) on IRIV IOC isolated RS485 (UART1)."""

import time

import board
import busio


def _crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


class ModbusRTU:
    """RS485 Modbus RTU master — auto DE/RE on IRIV hardware."""

    def __init__(self, baud=115200, timeout_s=1.0):
        self.timeout_s = timeout_s
        # board.UART / board.RS485 are the on-board UART1 (GP24 TX / GP25 RX).
        self.uart = busio.UART(
            board.TX,
            board.RX,
            baudrate=baud,
            bits=8,
            parity=None,
            stop=1,
            timeout=timeout_s,
        )

    def close(self):
        self.uart.deinit()

    def _flush_rx(self):
        while self.uart.in_waiting:
            self.uart.read(self.uart.in_waiting)

    def read_holding_registers(self, slave, address, count):
        """FC03: return list of `count` uint16 words (big-endian wire order)."""
        if count < 1 or count > 125:
            raise ValueError("count must be 1..125")

        req = bytearray(8)
        req[0] = slave & 0xFF
        req[1] = 0x03
        req[2] = (address >> 8) & 0xFF
        req[3] = address & 0xFF
        req[4] = (count >> 8) & 0xFF
        req[5] = count & 0xFF
        crc = _crc16(req[:6])
        req[6] = crc & 0xFF
        req[7] = (crc >> 8) & 0xFF

        self._flush_rx()
        self.uart.write(req)

        # Response: addr + fc + bytecount + 2*count data + CRC
        expect = 5 + 2 * count
        buf = bytearray()
        deadline = time.monotonic() + self.timeout_s
        while len(buf) < expect and time.monotonic() < deadline:
            n = self.uart.in_waiting
            if n:
                chunk = self.uart.read(n)
                if chunk:
                    buf.extend(chunk)
            else:
                time.sleep(0.001)

        if len(buf) < 5:
            raise OSError("Modbus timeout / short response")

        if buf[0] != (slave & 0xFF):
            raise OSError("Modbus slave mismatch")
        if buf[1] & 0x80:
            raise OSError("Modbus exception 0x%02X" % (buf[2] if len(buf) > 2 else 0))
        if buf[1] != 0x03:
            raise OSError("Unexpected FC 0x%02X" % buf[1])

        byte_count = buf[2]
        if byte_count != 2 * count:
            raise OSError("byte count %d != %d" % (byte_count, 2 * count))
        if len(buf) < 3 + byte_count + 2:
            raise OSError("Modbus truncated response")

        frame = buf[: 3 + byte_count + 2]
        got = frame[-2] | (frame[-1] << 8)
        if got != _crc16(frame[:-2]):
            raise OSError("Modbus CRC error")

        regs = []
        data = frame[3 : 3 + byte_count]
        for i in range(0, byte_count, 2):
            regs.append((data[i] << 8) | data[i + 1])
        return regs
