# Agent notes — JK-PB RS485 Monitor

Read **[docs/HANDOFF.md](docs/HANDOFF.md)** before changing Modbus maps or IRIV / ESP32 pollers.

## Project role

Monitor a **JK-PB\*** BMS over **Modbus RTU** on **UART1** (leftmost RJ45 labeled **RS485**). This is a **master** toolkit (PC / IRIV CircuitPython / future ESP32 RS485).

## Hard constraints

- Baud **115200** 8N1 (app UART protocol **001**), slave **15** (DIP all ON).
- Use **RS485**, not **CAN**, not **RS485-P** (parallel).
- **One master per bus.**
- If the same BMS is on CAN to a Deye inverter, prefer ESS battery telemetry via the **Deye** Modbus path (`deye-sg06-rs485-monitor`).

## IRIV IOC

- CircuitPython block-read — [`iriv-ioc/`](iriv-ioc/) ([install / MQTT broker](iriv-ioc/README.md), code in `firmware/`).
- HA device: **IRIV IOC - JK BMS** by **Cytron Technologies** — [`homeassistant/`](homeassistant/).
- Pack series: `JK_CELLS` / web `CELL_COUNT` / HA cell blocks = **4 | 8 | 16** (lab **8S**).
- Do **not** use stock IRIV MQTT Gateway job JSON (high latency).

## Out of scope here

- Stock IRIV MQTT Gateway job JSON (high latency; removed from this repo).

## Sister repo

`../deye-sg06-rs485-monitor` — Deye inverter @ 9600 / slave 1.

## Bench emulator

`emulator/jk-pb-emu.py` — JK-PB Modbus RTU **slave** (protocol **001** live map @ 0x1200). Use to exercise masters without a real BMS.
