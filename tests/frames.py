"""Frames for tests, with provenance."""

# A complete 0x16 status frame from a Jacuzzi J-series spa, published in
# DECODING.md section 3.9 of
# https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp and
# reused in the Jacuzzi-RS485 test suite. Monday 7 Nov 2022 16:18, Celsius,
# 19.0 C water and set point.
STATUS = bytes.fromhex(
    "7e25ffaf16"
    "1012270b16420026fa260a14018100004201"
    "1c00098000000a000000ff000000"
    "2f7e"
)

# Captured set-temperature and module-ident frames (Jacuzzi-RS485 issues 54
# and 62); only used to check the CRC against real traffic.
SET_TEMP_20C = bytes.fromhex("7e060abf2028ca7e")
MODULE_IDENT_REQ = bytes.fromhex("7e050abf04777e")
