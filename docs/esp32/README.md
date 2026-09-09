# ESP32 / ESP32-S3 + UART → RS485 poller (JK-PB)

**Status:** guide stub — implement next.

## Goal

Modbus RTU **master** on ESP32/S3 → JK UART1 (leftmost RJ45 **RS485**), publish MQTT aligned with `jkbms-iriv-ioc-config.json` (`iriv/jkbms/...`).

## Constraints

| Item | Value |
|------|--------|
| Baud | **115200** 8N1 |
| Slave | **15** |
| App | UART1 protocol **001** |
| Bus | One master; not the CAN port; not RS485-P |

## Registers

Use the map in `jk-pb-modbus-read.py` / `_gen_jkbms_iriv_jobs.py` (pack V/I/P as u32/s32, cells as u16 mV).
