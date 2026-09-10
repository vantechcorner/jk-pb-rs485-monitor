# IRIV IOC — JK BMS MQTT

CircuitPython firmware for the **Cytron IRIV IO Controller**: Modbus RTU master on isolated RS485 → MQTT topics `iriv/jkbms/...`.

Datasheet: [IRIV IO Controller Datasheet.md](IRIV%20IO%20Controller%20Datasheet.md)  
Full technical notes: [firmware/README.md](firmware/README.md)

## Install

1. Flash **CircuitPython** for board `cytron_iriv_io_controller`:  
   https://circuitpython.org/board/cytron_iriv_io_controller/
2. Copy everything under [`firmware/`](firmware/) onto the `CIRCUITPY` drive:

```text
CIRCUITPY/
  code.py
  settings.toml
  lib/          # app modules + vendored Adafruit .mpy
```

PowerShell example (drive letter may differ):

```powershell
$src = "D:\Github\jk-pb-rs485-monitor\iriv-ioc\firmware"
Copy-Item "$src\settings.toml","$src\code.py" E:\ -Force
Copy-Item "$src\lib\*" E:\lib\ -Recurse -Force
```

3. Wire JK BMS monitor port (**RS485** / UART1) to the IRIV RS485 terminals.  
   Defaults: **115200** 8N1, slave **15**. One Modbus master on the bus.
4. Plug Ethernet (DHCP). Soft-reset the board. USB serial should show IP, MQTT connect, then `OK V=…`.

## MQTT broker settings

Edit **[`firmware/settings.toml`](firmware/settings.toml)** (also on `CIRCUITPY/settings.toml` after deploy), then reset:

```toml
MQTT_BROKER = "172.16.10.40"   # broker host or IP
MQTT_PORT = 1883
MQTT_BASE = "iriv/jkbms"       # topic prefix
MQTT_CLIENT_ID = "iriv-ioc-jkbms"
MQTT_USER = ""                 # optional
MQTT_PASS = ""
MQTT_QOS = 1
MQTT_RETAIN = "true"
```

| Key | Purpose |
|-----|---------|
| `MQTT_BROKER` | Broker address |
| `MQTT_PORT` | Usually `1883` |
| `MQTT_BASE` | Topic root (`…/pack/voltage`, `…/cells/1`, …) |
| `MQTT_USER` / `MQTT_PASS` | Leave empty if anonymous |

Pack series (`JK_CELLS` = 4 / 8 / 16) is also in the same file.
