# JK-PB Modbus RTU slave emulator

Bench stand-in for a real **JK-PB\*** BMS on UART1 (protocol **001**). Speaks the same live FC03 map as [`jk-pb-modbus-read.py`](../jk-pb-modbus-read.py) and [`iriv-ioc/firmware/`](../iriv-ioc/firmware/).

```bash
pip install -r ../requirements.txt
python jk-pb-emu.py --port COM36 --cells 8 --debug --scenario day
```

| Option | Default |
|--------|---------|
| `--slave-id` | 15 |
| `--baudrate` | 115200 |
| `--cells` | 8 (also 4 / 16) |
| `--scenario` | day \| night \| cloud \| fault |

Use a **separate** USB-RS485 adapter from any live master under test (one master per bus).
