# SPDX-License-Identifier: MIT
"""W5500 Ethernet init (DHCP) for Cytron IRIV IOC."""

import time

import board
import busio
import digitalio
from adafruit_wiznet5k.adafruit_wiznet5k import WIZNET5K
import adafruit_wiznet5k.adafruit_wiznet5k_socketpool as socketpool


def init_ethernet(timeout_s=120.0, link_wait_s=90.0):
    """Reset W5500, wait for cable link, DHCP, return (eth, pool)."""
    cs = digitalio.DigitalInOut(board.W5500_CS)
    rst = digitalio.DigitalInOut(board.W5500_RST)
    rst.switch_to_output(value=True)
    rst.value = False
    time.sleep(0.05)
    rst.value = True
    time.sleep(0.15)

    spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)

    # Bring PHY up without DHCP first (unplugged cable must not crash).
    eth = WIZNET5K(spi, cs, is_dhcp=False)

    print("ETH: waiting for cable link…")
    link_deadline = time.monotonic() + link_wait_s
    while time.monotonic() < link_deadline:
        if eth.link_status:
            print("ETH: link up")
            break
        time.sleep(0.5)
    else:
        raise ConnectionError("Ethernet cable/link not detected")

    print("ETH: requesting DHCP…")
    # CircuitPython wiznet5k: set_dhcp() has no timeout kwarg on many builds.
    try:
        eth.set_dhcp()
    except Exception as exc:
        print("ETH set_dhcp:", exc)

    dhcp_deadline = time.monotonic() + timeout_s
    while time.monotonic() < dhcp_deadline:
        if not eth.link_status:
            print("ETH: link lost, waiting…")
            time.sleep(1.0)
            continue
        try:
            if hasattr(eth, "maintain_dhcp"):
                eth.maintain_dhcp()
        except Exception as exc:
            print("ETH maintain_dhcp:", exc)

        ip_raw = eth.ip_address
        if ip_raw and ip_raw != b"\x00\x00\x00\x00":
            ip = eth.pretty_ip(ip_raw)
            if ip and ip != "0.0.0.0":
                print("ETH: IP", ip)
                pool = socketpool.SocketPool(eth)
                return eth, pool
        time.sleep(0.5)

    raise RuntimeError("Ethernet DHCP timed out")
