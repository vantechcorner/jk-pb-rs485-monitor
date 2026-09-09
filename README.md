# JK-PB RS485 Monitor

Field tools to **monitor** a JiKong **JK-PB\*** BMS over **Modbus RTU (RS485)** on UART1: PC poller, IRIV IOC MQTT template, BLE sketch stub, and (planned) ESP32 UART→RS485 poller.

> Vietnamese: [README-vn.md](README-vn.md)

**Sister project:** [deye-sg06-rs485-monitor](../deye-sg06-rs485-monitor) — Deye inverter Modbus (separate bus @ 9600).

```text
  [ PC / IRIV / ESP32 ]  = Modbus MASTER
              |
         RS485 A/B @ 115200
              |
  [ JK-PB* UART1 / leftmost RJ45 RS485 ]  = Modbus SLAVE
```

**One master per bus.** Do not share the cable with Deye datalogger RS485 or the inverter **CAN** link.

```bash
pip install -r requirements.txt
```

---

## Field-tested

| Hardware | Verified |
|----------|----------|
| **JK-PB1A16S10P** on **24 V 8S** (~50 Ah) research pack | UART1 protocol **001**, slave **15**, **115200** — PC poller + live cells/SOC/V/I |
| Same BMS family on **16S 51.2 V 100 Ah** with Deye | Inverter link = **CAN**; for ESS telemetry prefer Deye Modbus (sister repo) |

![JK-PB1A16S10P main board](docs/images/jk-pb1a16s10p-board.jpg)

![JK I/O board — RS485 / CAN / RS485-P](docs/images/jk-pb-io-board-rs485.jpg)

*I/O left → right: **RS485** (UART1) · **CAN** · middle RJ45 · **RS485-P** ×2. Pins: 1/8=B, 2/7=A, 3/6=GND.*

![JK app settings](docs/images/jk-app-uart-settings.png)

*Device Address **15**; UART1/2 = **001** JK BMS RS485 Modbus; UART3 = **015** parallel.*

<!-- Placeholder -->
![Setup — 24 V 8S pack](docs/images/setup-jk-24v-8s.jpg)

*Placeholder: save as `docs/images/setup-jk-24v-8s.jpg`.*

---

## What's in this repo

| Area | Files |
|------|--------|
| **PC poller (master)** | `jk-pb-modbus-read.py` |
| **IRIV IOC MQTT** | `jkbms-iriv-ioc-config.json`, `_gen_jkbms_iriv_jobs.py` |
| **BLE (optional)** | `jkbms-ble-gateway.yaml` (needs external component) |
| **ESP32 poller** | `docs/esp32/README.md` (guide stub) |

---

## Key Modbus parameters

| Parameter | Value |
|-----------|--------|
| Port | Leftmost RJ45 **RS485** (UART1) |
| Baud | **115200** 8N1 (app `001`) |
| Slave ID | **15** (DIP all ON) |
| Protocol | JK BMS RS485 Modbus V1.0 |

Key regs: cells `0x1200+`; pack V `0x1290` u32×0.001; current `0x1298` s32×0.001; SOC low byte `0x12A6`.

### PC poller

```bash
python jk-pb-modbus-read.py --port COM35 --cells 8
python jk-pb-modbus-read.py --port COM35 --cells 8 --once --full
```

### IRIV

```bash
python _gen_jkbms_iriv_jobs.py
```

Import `jkbms-iriv-ioc-config.json`. MQTT base: `iriv/jkbms`. Confirm UINT32/INT32 on pack V/I/P jobs after import.

**IRIV limit:** do not exceed **26** enabled poll jobs on the gateway firmware used in lab (27th → reboot + wipe). This JK template stays under that when used alone; do not merge with a full Deye job set on the **same** IRIV without trimming.

---

## ESP32 / S3 + UART→RS485 (planned)

See [docs/esp32/README.md](docs/esp32/README.md).

---

## License / lab note

Lab toolkit for BMS research. Not a substitute for the inverter CAN BMS link on a live ESS.
