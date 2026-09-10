# JK-PB RS485 Monitor

Field tools to **monitor** a JiKong **JK-PB\*** BMS over **Modbus RTU (RS485)** on UART1: PC poller, Cytron **IRIV IOC** CircuitPython MQTT firmware (block read), web dashboard, Home Assistant sensors, JK Modbus slave emulator, and (planned) ESP32 RS485 poller.

> Vietnamese: [README-vn.md](README-vn.md)  
> **Cursor / agent handoff:** [AGENTS.md](AGENTS.md) · [docs/HANDOFF.md](docs/HANDOFF.md) · `.cursor/rules/lab-context.mdc`

**Tested by Van Tech Corner.**  
**License:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](LICENSE).

> **Disclaimer / Cảnh báo an toàn:** Work carefully with batteries and BMS hardware. Short circuits or wiring mistakes can cause fire or explosion. / Hãy cẩn thận khi làm việc với pin và mạch BMS; chập mạch có thể gây cháy nổ.

**Sister project:** [deye-sg06-rs485-monitor](../deye-sg06-rs485-monitor) — Deye inverter Modbus (separate bus @ 9600).

```text
  [ PC / IRIV IOC / ESP32 ]  = Modbus MASTER
              |
         RS485 A/B @ 115200
              |
  [ JK-PB* UART1 / leftmost RJ45 RS485 ]  = Modbus SLAVE
              |
         IRIV → MQTT iriv/jkbms/#  →  web / Home Assistant
```

**One master per bus.** Do not share the cable with Deye datalogger RS485 or the inverter **CAN** link.

```bash
pip install -r requirements.txt
```

---

## Field-tested

| Hardware | Verified |
|----------|----------|
| **JK-PB1A16S10P** on **24 V 8S** (~50 Ah) research pack | UART1 **001**, slave **15**, **115200** — PC poller |
| **IRIV IOC** CircuitPython firmware | Block FC03 → MQTT `172.16.10.40` / `iriv/jkbms/#` |
| Web dashboard + Home Assistant MQTT | Live pack/cells OK (device **IRIV IOC - JK BMS**) |
| Same BMS family on **16S 51.2 V 100 Ah** with Deye | Inverter = **CAN**; ESS telemetry via Deye Modbus (sister repo) |

![JK-PB1A16S10P main board](docs/images/jk-pb1a16s10p-board.jpg)

![JK I/O board — RS485 / CAN / RS485-P](docs/images/jk-pb-io-board-rs485.jpg)

*I/O left → right: **RS485** (UART1) · **CAN** · middle RJ45 · **RS485-P** ×2. Pins: 1/8=B, 2/7=A, 3/6=GND.*

![JK app settings](docs/images/jk-app-uart-settings.png)

*Device Address **15**; UART1/2 = **001** JK BMS RS485 Modbus; UART3 = **015** parallel.*

![Setup — 24 V 8S pack](docs/images/setup-jk-24v-8s.jpg)

*Lab 24 V 8S research pack with JK-PB monitor path.*

---

## Screenshots — IRIV IOC - JK BMS

![Web dashboard](docs/images/IRIV-IOC-JK-BMS-Web.png)

*MQTT web UI (`web/`) — pack, SOC, cells (8S).*

![Home Assistant device](docs/images/IRIV-IOC-JK-BMS-Home-Assistant.png)

*Home Assistant device **IRIV IOC - JK BMS** (Cytron Technologies).*

![Home Assistant sensor YAML](docs/images/IRIV-IOC-JK-BMS-Home-Assistant-Sensor-Config.png)

*Manual MQTT sensor package in HA.*

---

## What's in this repo

| Area | Files |
|------|--------|
| **PC poller (master)** | `jk-pb-modbus-read.py` |
| **IRIV IOC** | [`iriv-ioc/`](iriv-ioc/) — install + MQTT broker: [`iriv-ioc/README.md`](iriv-ioc/README.md); firmware in `iriv-ioc/firmware/` |
| **Web dashboard** | [`web/`](web/) — MQTT over WebSockets (`iriv/jkbms/#`) |
| **Home Assistant** | [`homeassistant/`](homeassistant/) — device **IRIV IOC - JK BMS** by Cytron Technologies |
| **Bench JK slave** | [`emulator/`](emulator/) — `jk-pb-emu.py` (JK protocol **001** live map) |
| **ESP32 RS485 poller** | [`esp32/`](esp32/) (stub) |
| **Datasheet** | [`iriv-ioc/`](iriv-ioc/) |

Pack series **4S / 8S / 16S**: set `JK_CELLS` in firmware `settings.toml`, `CELL_COUNT` in `web/app.js`, and matching cell blocks in the HA YAML (lab default **8S**).

Stock IRIV **MQTT Gateway** per-register JSON is **not** used (high latency).

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

### IRIV IOC

Install and set the MQTT broker in [`iriv-ioc/README.md`](iriv-ioc/README.md).

- Copy `iriv-ioc/firmware/` → CIRCUITPY  
- Edit **`settings.toml`**: `MQTT_BROKER`, `MQTT_PORT`, `MQTT_BASE`, …  
- Lab default broker: `172.16.10.40:1883`, base `iriv/jkbms`  
- **One Modbus master** on the JK RS485 bus

### Web dashboard

```bash
cd web && python -m http.server 8081
```

Open `http://127.0.0.1:8081`. Broker WebSocket (lab): `ws://172.16.10.40:9001`, prefix `iriv/jkbms`. See [web/README.md](web/README.md).

### Home Assistant

```text
homeassistant/mqtt_cytron_iriv_ioc_jkbms.yaml
```

Device **IRIV IOC - JK BMS** · manufacturer **Cytron Technologies**. See [homeassistant/README.md](homeassistant/README.md).

### JK Modbus slave emulator (bench)

```bash
python emulator/jk-pb-emu.py --port COM36 --cells 8 --debug --scenario day
```

Defaults: slave **15**, **115200**. See [emulator/README.md](emulator/README.md).

---

## ESP32 / S3 + UART→RS485 (planned)

See [esp32/README.md](esp32/README.md).

---

## License / credit / safety

- **License:** [CC BY 4.0](LICENSE) (Creative Commons Attribution 4.0 International)
- **Tested by:** Van Tech Corner
- **Disclaimer:** Be careful when working with batteries and BMS circuits. Short circuits can cause fire or explosion. This is a lab toolkit, not a substitute for the inverter CAN BMS link on a live ESS.
