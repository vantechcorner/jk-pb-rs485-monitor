# IRIV IOC - JK BMS → MQTT (CircuitPython)

Lean firmware for **Cytron Technologies** IRIV IOC: **one Modbus FC03 block** (`0x1200`, 98 words) → decode → publish `iriv/jkbms/...`.

**Install + MQTT broker settings:** see parent [`../README.md`](../README.md).

Works with [`web/`](../../web/) and Home Assistant device **IRIV IOC - JK BMS**.

**One Modbus master per bus.**

## Hardware

| Item | Value |
|------|--------|
| Board | Cytron IRIV IO Controller (RP2350 + W5500) |
| RS485 | Isolated UART1 (`board.TX`/`RX` = GP24/25), auto DE/RE |
| JK BMS | UART1 app protocol **001**, slave **15**, **115200** 8N1 |
| Cells | `JK_CELLS` in `settings.toml`: **4 / 8 / 16** (one active; others commented) |
| Ethernet | W5500, **DHCP** |
| Broker | `172.16.10.40:1883` (edit `settings.toml`) |

## Flash CircuitPython

1. Download UF2 for **IRIV IO Controller**:  
   https://circuitpython.org/board/cytron_iriv_io_controller/
2. Hold **BOOT**, tap **RESET**, release BOOT → `RPI-RP2` drive.
3. Copy the UF2 onto the drive; board reboots as `CIRCUITPY`.

## Adafruit libraries

Vendored under [`lib/`](lib/) (CircuitPython **9.x** `.mpy`, lab build 9.2.8):

- `adafruit_wiznet5k/`, `adafruit_minimqtt/`, `adafruit_bus_device/`
- `adafruit_connection_manager.mpy`, `adafruit_ticks.mpy`

Copy the whole `lib/` folder to `CIRCUITPY/lib/`.

Optional refresh via [circup](https://learn.adafruit.com/keep-your-circuitpython-libraries-up-to-date-with-circup) or the [9.x Bundle](https://circuitpython.org/libraries).

## Deploy

```text
settings.toml
code.py
lib/          # app + vendored Adafruit libs
```

```powershell
$src = "D:\Github\jk-pb-rs485-monitor\iriv-ioc\firmware"
Copy-Item "$src\settings.toml","$src\code.py" E:\ -Force
Copy-Item "$src\lib\*" E:\lib\ -Recurse -Force
```

USB serial: DHCP IP → MQTT connect → `OK V=…` (or `POLL fail` until RS485 is wired).

## Verify

```bash
mosquitto_sub -h 172.16.10.40 -t 'iriv/jkbms/#' -v
```

## Files

| File | Role |
|------|------|
| `code.py` | Main loop: poll ~1 s → MQTT |
| `lib/jk_bms.py` | Live-block decode (same map as `jk-pb-modbus-read.py`) |
| `lib/iriv_rs485.py` | Minimal Modbus RTU FC03 master |
| `lib/iriv_eth.py` | W5500 + DHCP (waits for link) |
| `lib/mqtt_publish.py` | MiniMQTT helpers |

## Troubleshooting

- **Modbus timeout:** A/B swap, termination, one master only, baud 115200 / slave 15.
- **DHCP hang:** check Ethernet link; broker must reach the leased IP.
- **MQTT refused:** `allow_anonymous` or set `MQTT_USER` / `MQTT_PASS`.
