"""Frames for tests, with provenance."""

# A complete 0x16 status frame from a Jacuzzi J-series spa, published in
# DECODING.md section 3.9 of
# https://github.com/HyperActiveJ/sundance780-jacuzzi-balboa-rs485-tcp and
# reused in the Jacuzzi-RS485 test suite. Monday 7 Nov 2022 16:18, Celsius,
# 19.0 C water and set point (Celsius is sent in half-degrees).
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

# J-480 via ProLink, idle, from the integration's diagnostics (2026-11-15).
# Celsius, 18.5 C water and set point (confirmed on the topside panel),
# all pumps off. The spa clock was unset
# (2 Jan 2014 12:52).
J480_STATUS = bytes.fromhex(
    "7e25ffaf160c3182010e920025fa2500000087000044020000008000004e"
    "00030103000000387e"
)
J480_LIGHTS = bytes.fromhex(
    "7e21ffaf2300000000000000010064000000ff0000000000000000000000000000e67e"
)

# The same J-480 straight after "Sync spa clock" was pressed at 21:52 on
# Sunday 15 Nov 2026 (Europe/London): the spa accepted the 0x18 command and
# worked out the day of the week itself (0 = Sunday).
J480_STATUS_AFTER_CLOCK_SYNC = bytes.fromhex(
    "7e25ffaf1615340f0b1a920025fa2500000083000044020000008000004e"
    "00030103000000ba7e"
)

# The same J-480 after the target was raised from 18.5 to 20.5 C from Home
# Assistant (22:00, 15 Nov 2026). The spa accepted it and started its
# circulation pump on high to heat (confirmed by the owner).
J480_STATUS_SET_20_5 = bytes.fromhex(
    "7e25ffaf1616000f0b1a920025fa2902060183000044020000008000004e"
    "00030103000000637e"
)

# The same J-480 with the jets switched from the topside panel (22:24,
# 15 Nov 2026). The circulation pump was running throughout. Single-speed
# jets report as 2 ("high").
J480_STATUS_JETS_1_ON = bytes.fromhex(
    "7e25ffaf1616180f0b1a920025fa250a0501030000490200016d8000004e"
    "00030100000000f27e"
)
J480_STATUS_JETS_OFF = bytes.fromhex(
    "7e25ffaf1616180f0b1a920025fa25020501030000490200016d8000004e"
    "000301000000006c7e"
)
J480_STATUS_JETS_2_ON = bytes.fromhex(
    "7e25ffaf1616180f0b1a920025fa25220501030000490200016d8000004e"
    "000301000000001a7e"
)
# Lights on (colour-cycling mode 6) and then off, same session
J480_LIGHTS_ON = bytes.fromhex(
    "7e21ffaf23800664005ca200010064000000ff00000000000000010064000000ff277e"
)
J480_LIGHTS_OFF = bytes.fromhex(
    "7e21ffaf2300000000000000010064000000ff00000000000000010064000000ffe97e"
)
