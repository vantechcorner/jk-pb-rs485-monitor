# HANDOFF — JK-PB RS485 Monitor

**Audience:** future Cursor chats / humans opening this repo cold.  
**Status:** Field-validated lab toolkit (Monitor), split from umbrella `Inverter-BMS-RS485-Emulator`.

---

## 1. What this project is

Tools to **read** JiKong **JK-PB\*** BMS telemetry over **Modbus RTU** on the monitor RS485 port (UART1):

1. Wiring / app / register notes (+ photos)  
2. Python **Modbus master** poller for PC + USB-RS485  
3. Cytron **IRIV IOC** — CircuitPython block-read MQTT firmware ([`iriv-ioc/firmware/`](../iriv-ioc/firmware/))  
4. Web dashboard + Home Assistant (**IRIV IOC - JK BMS** / Cytron Technologies)  
5. Planned: **ESP32/S3 + UART→RS485** master (`esp32/`)
6. Optional **JK-PB Modbus slave emulator** (`emulator/jk-pb-emu.py`) for bench without a real BMS  

Stock IRIV MQTT Gateway JSON was removed (high latency).

**Not in scope:** replacing the inverter **CAN** BMS link.

---

## 2. Lab topology

### Setup B — research pack (this repo’s primary path)

```text
Waveshare USB-RS485 ──RS485@115200──► JK I/O "RS485" (UART1) ── slave 15
         ▲
   PC: jk-pb-modbus-read.py
   or IRIV IOC CircuitPython firmware → MQTT iriv/jkbms/#
```

Example live read (8S): ~26.56 V, SOC ~67%, 33.5/50 Ah, cell Δ ~1–3 mV.

### Setup A — ESS with Deye (do not Modbus-fight CAN)

```text
JK ──CAN──► Deye ──RS485@9600──► IRIV (iriv/ivt)   ← use deye-sg06-rs485-monitor
```

---

## 3. Hardware / pinout

Photos in `docs/images/`:

- `jk-pb1a16s10p-board.jpg` — main BMS  
- `jk-pb-io-board-rs485.jpg` — I/O V1.02 + pin table  
- `jk-app-uart-settings.png` — address 15, UART 001/001/015  

| Port | Use |
|------|-----|
| RS485 (left) | Modbus monitor |
| CAN | Inverter only |
| RS485-P | Pack parallel |

---

## 4. PC poller

```bash
pip install -r requirements.txt
python jk-pb-modbus-read.py --port COMxx --cells 8
python jk-pb-modbus-read.py --port COMxx --cells 8 --once --full --trace
```

`--full` also reads protection block `0x1000` and device info `0x1400` (model/HW/SW/SN).

---

## 5. IRIV

CircuitPython block-read firmware — see [`iriv-ioc/firmware/README.md`](../iriv-ioc/firmware/README.md).

- One FC03 live block `0x1200` × 98 words → decode → MQTT `iriv/jkbms/...` @ **172.16.10.40** (DHCP on W5500).
- **One master only** on that RS485 bus.
- Pack series: `JK_CELLS` = **4 | 8 | 16** (lab **8S**); keep web `CELL_COUNT` and HA cell blocks in sync.
- Consumers: [`web/`](../web/), Home Assistant device **IRIV IOC - JK BMS** ([`homeassistant/`](../homeassistant/)) by **Cytron Technologies**.
- Web dashboard marks broker **retain** vs **live** publishes in the status bar.

Stock IRIV **MQTT Gateway** per-register job JSON is **not** maintained here (high poll latency).

---

## 6. Register cheat sheet

| Addr | Type | Scale | Meaning |
|------|------|-------|---------|
| `0x1200+2n` | u16 | ×0.001 V | Cell n |
| `0x1244` / `0x1246` | u16 | ×0.001 V | Avg / Δmax |
| `0x128A` | s16 | ×0.1 °C | MOS |
| `0x1290` | u32 | ×0.001 V | Pack V |
| `0x1294` | s32 | ×0.001 W | Power |
| `0x1298` | s32 | ×0.001 A | Current |
| `0x12A6` | u16 | low = SOC % | high = bal state |
| `0x12A8` / `0x12AC` | s32/u32 | ×0.001 Ah | Remain / full |

Community refs used during research: phinix / esphome-jk-bms / YamBMS JK-PB docs (protocol **001**).

---

## 7. Next work (ESP32)

Implement `esp32/README.md`: ESP32-S3 master @ 115200 → same MQTT topics as IRIV JK config.

---

## 8. Sister repo

| Item | Deye monitor |
|------|----------------|
| Path | `../deye-sg06-rs485-monitor` |
| Baud | 9600 |
| Slave | 1 |
| MQTT | `iriv/ivt/...` |
| Note | IRIV job cap 26; no PV2 on that site template |
