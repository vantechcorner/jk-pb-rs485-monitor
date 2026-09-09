"""Generate JK-PB Modbus poll jobs for IRIV IOC MQTT Gateway.

Updates jkbms-iriv-ioc-config.json in place (system/network/io preserved).
Protocol: JK BMS RS485 Modbus V1.0 (UART1 = 001), slave 15, 115200 8N1.

Run: python _gen_jkbms_iriv_jobs.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DST = ROOT / "jkbms-iriv-ioc-config.json"
SRC = DST  # self-contained template

# Field-verified on Deye IRIV export: dataType 3 = s16.
# 32-bit enums are not exported yet — UI labels should read u32/s32.
# If pack V/I look wrong after import, open IRIV job and pick UINT32/INT32.
S16 = 3
U32 = 4
S32 = 5

SLAVE = 15
CELLS = 8  # 24 V pack; change and re-run for 16S


def job(
    name: str,
    addr: int,
    *,
    count: int = 1,
    dtype: int = S16,
    scale: float = 1.0,
    offset: float = 0.0,
    unit: str = "",
    decimals: int = 2,
    topic: str = "",
    period_ms: int = 1000,
) -> dict:
    return {
        "enabled": True,
        "name": name,
        "slaveId": SLAVE,
        "fc": 3,
        "address": addr,
        "count": count,
        "dataType": dtype,
        "byteOrder": 0,  # ABCD / high-word first (matches JK u32/s32)
        "scale": scale,
        "offset": offset,
        "unit": unit,
        "decimals": decimals,
        "periodMs": period_ms,
        "priority": 1,
        "topicSuffix": topic,
        "payload": 1,
        "qos": 1,
        "retain": True,
        "publishMode": 1,
        "deadband": 0,
        "minPublishIntervalMs": 0,
    }


def empty() -> dict:
    return {
        "enabled": False,
        "name": "",
        "slaveId": 0,
        "fc": 0,
        "address": 0,
        "count": 0,
        "dataType": 0,
        "byteOrder": 0,
        "scale": 0,
        "offset": 0,
        "unit": "",
        "decimals": 0,
        "periodMs": 0,
        "priority": 0,
        "topicSuffix": "",
        "payload": 0,
        "qos": 0,
        "retain": False,
        "publishMode": 0,
        "deadband": 0,
        "minPublishIntervalMs": 0,
    }


LIVE_MS = 1000
TEMP_MS = 10000
SLOW_MS = 30000

# Doc addresses (hex) — same as ESPHome / jk-pb-modbus-read.py
jobs: list[dict] = [
    # --- Pack live ---
    job(
        "Pack Voltage",
        0x1290,
        count=2,
        dtype=U32,
        scale=0.001,
        unit="V",
        decimals=3,
        topic="pack/voltage",
        period_ms=LIVE_MS,
    ),
    job(
        "Pack Current",
        0x1298,
        count=2,
        dtype=S32,
        scale=0.001,
        unit="A",
        decimals=3,
        topic="pack/current",
        period_ms=LIVE_MS,
    ),
    job(
        "Pack Power",
        0x1294,
        count=2,
        dtype=S32,
        scale=0.001,
        unit="W",
        decimals=1,
        topic="pack/power",
        period_ms=LIVE_MS,
    ),
    # SOC = low byte of 0x12A6; high byte = balance state (0 when idle)
    job(
        "SOC",
        0x12A6,
        dtype=S16,
        scale=1,
        unit="%",
        decimals=0,
        topic="pack/soc",
        period_ms=LIVE_MS,
    ),
    job(
        "Balance Current",
        0x12A4,
        dtype=S16,
        scale=0.001,
        unit="A",
        decimals=3,
        topic="pack/balance_current",
        period_ms=LIVE_MS,
    ),
    job(
        "Cell Average",
        0x1244,
        dtype=S16,
        scale=0.001,
        unit="V",
        decimals=3,
        topic="cells/average",
        period_ms=LIVE_MS,
    ),
    job(
        "Cell Delta Max",
        0x1246,
        dtype=S16,
        scale=0.001,
        unit="V",
        decimals=3,
        topic="cells/delta_max",
        period_ms=LIVE_MS,
    ),
    # --- Temperatures ---
    job(
        "MOS Temperature",
        0x128A,
        dtype=S16,
        scale=0.1,
        unit="°C",
        decimals=1,
        topic="temp/mos",
        period_ms=TEMP_MS,
    ),
    job(
        "Battery Temp 1",
        0x129C,
        dtype=S16,
        scale=0.1,
        unit="°C",
        decimals=1,
        topic="temp/battery1",
        period_ms=TEMP_MS,
    ),
    job(
        "Battery Temp 2",
        0x129E,
        dtype=S16,
        scale=0.1,
        unit="°C",
        decimals=1,
        topic="temp/battery2",
        period_ms=TEMP_MS,
    ),
    # --- Capacity / status (slow) ---
    job(
        "Remain Capacity",
        0x12A8,
        count=2,
        dtype=S32,
        scale=0.001,
        unit="Ah",
        decimals=2,
        topic="pack/remain_ah",
        period_ms=SLOW_MS,
    ),
    job(
        "Full Capacity",
        0x12AC,
        count=2,
        dtype=U32,
        scale=0.001,
        unit="Ah",
        decimals=2,
        topic="pack/full_ah",
        period_ms=SLOW_MS,
    ),
    job(
        "Cycle Count",
        0x12B0,
        count=2,
        dtype=U32,
        scale=1,
        unit="",
        decimals=0,
        topic="pack/cycles",
        period_ms=SLOW_MS,
    ),
    job(
        "SOH",
        0x12B8,
        dtype=S16,
        scale=1,
        unit="%",
        decimals=0,
        topic="pack/soh",
        period_ms=SLOW_MS,
    ),
    job(
        "Alarm Mask",
        0x12A0,
        count=2,
        dtype=U32,
        scale=1,
        unit="",
        decimals=0,
        topic="pack/alarm",
        period_ms=SLOW_MS,
    ),
    job(
        "Runtime",
        0x12BC,
        count=2,
        dtype=U32,
        scale=1,
        unit="s",
        decimals=0,
        topic="pack/runtime_s",
        period_ms=SLOW_MS,
    ),
]

# Cell voltages: doc addresses 0x1200, 0x1202, … (stride 2)
for n in range(CELLS):
    jobs.append(
        job(
            f"Cell {n + 1}",
            0x1200 + 2 * n,
            dtype=S16,
            scale=0.001,
            unit="V",
            decimals=3,
            topic=f"cells/{n + 1}",
            period_ms=LIVE_MS,
        )
    )

assert len(jobs) <= 32, len(jobs)
while len(jobs) < 32:
    jobs.append(empty())

cfg = json.loads(SRC.read_text(encoding="utf-8"))
cfg["rtu"]["link"]["baud"] = 115200
cfg["rtu"]["link"]["responseTimeoutMs"] = 800
cfg["rtu"]["pollJobs"] = jobs
cfg["mqtt"]["enabled"] = True
cfg["mqtt"]["host"] = "iriv-pi-control"
cfg["mqtt"]["baseTopic"] = "iriv/jkbms"
cfg["mqtt"]["clientId"] = "iriv-ioc-jkbms"
cfg["system"]["deviceName"] = "IRIV-IOC JK-BMS"

DST.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
enabled = [j for j in jobs if j["enabled"]]
print(f"Wrote {DST.name}: {len(enabled)} enabled jobs / 32 slots")
print(f"  baud={cfg['rtu']['link']['baud']} slave={SLAVE} base={cfg['mqtt']['baseTopic']}")
for j in enabled:
    print(
        f"  {j['name']:22} 0x{j['address']:04X}×{j['count']} "
        f"dt={j['dataType']} -> {cfg['mqtt']['baseTopic']}/{j['topicSuffix']}"
    )
