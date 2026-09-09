# HANDOFF — JK-PB RS485 Monitor

**Audience:** future Cursor chats / humans opening this repo cold.  
**Status:** Field-validated lab toolkit (Monitor), split from umbrella `Inverter-BMS-RS485-Emulator`.

---

## 1. What this project is

Tools to **read** JiKong **JK-PB\*** BMS telemetry over **Modbus RTU** on the monitor RS485 port (UART1):

1. Wiring / app / register notes (+ photos)  
2. Python **Modbus master** poller for PC + USB-RS485  
3. Cytron **IRIV IOC MQTT** JSON template  
4. Optional BLE ESPHome stub  
5. Planned: **ESP32/S3 + UART→RS485** master (`docs/esp32/`)

**Not in scope:** replacing the inverter **CAN** BMS link; Pylon-style emulator (lives with Deye repo as optional bench slave).

---

## 2. Lab topology

### Setup B — research pack (this repo’s primary path)

```text
Waveshare USB-RS485 ──RS485@115200──► JK I/O "RS485" (UART1) ── slave 15
         ▲
   PC: jk-pb-modbus-read.py
   or IRIV → MQTT iriv/jkbms/#
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

```bash
python _gen_jkbms_iriv_jobs.py
```

- Updates `jkbms-iriv-ioc-config.json` **in place** (no dependency on Deye JSON).  
- Slave **15**, baud **115200**, topics under `iriv/jkbms/`.  
- Lab IRIV firmware: **≤26 enabled jobs** or reboot/wipe.

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

Implement `docs/esp32/README.md`: ESP32-S3 master @ 115200 → same MQTT topics as IRIV JK config.

---

## 8. Sister repo

| Item | Deye monitor |
|------|----------------|
| Path | `../deye-sg06-rs485-monitor` |
| Baud | 9600 |
| Slave | 1 |
| MQTT | `iriv/ivt/...` |
| Note | IRIV job cap 26; no PV2 on that site template |
