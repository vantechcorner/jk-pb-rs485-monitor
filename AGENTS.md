# Agent notes — JK-PB RS485 Monitor

Read **[docs/HANDOFF.md](docs/HANDOFF.md)** before changing Modbus maps, IRIV JSON, or ESP32 pollers.

## Project role

Monitor a **JK-PB\*** BMS over **Modbus RTU** on **UART1** (leftmost RJ45 labeled **RS485**). This is a **master** toolkit (PC / IRIV / future ESP32).

## Hard constraints

- Baud **115200** 8N1 (app UART protocol **001**), slave **15** (DIP all ON).
- Use **RS485**, not **CAN**, not **RS485-P** (parallel).
- **One master per bus.**
- If the same BMS is on CAN to a Deye inverter, prefer ESS battery telemetry via the **Deye** Modbus path (`deye-sg06-rs485-monitor`).

## Sister repo

`../deye-sg06-rs485-monitor` — Deye inverter @ 9600 / slave 1.
