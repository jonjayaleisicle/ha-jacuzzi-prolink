"""Jacuzzi ProLink / RS-485 panel protocol, with no I/O.

Adapted from ``app/protocol.py`` of Jacuzzi-RS485 by Jack Brown and
contributors (https://github.com/jackbrown1993/Jacuzzi-RS485), licensed under
the Apache License 2.0. Changes: trimmed to the read-only parts, added the
0x23 lights message, type hints for Python 3.13. See NOTICE.

Frame layout (all values are bytes)::

    7E | LEN | DST | PF | TYPE | PAYLOAD ... | CRC | 7E

LEN counts itself, DST, PF, TYPE, PAYLOAD and CRC, so the whole frame is
LEN + 2 bytes. The CRC covers LEN through PAYLOAD.

Offsets used by the parsers are into the *whole* frame including the leading
0x7E, so ``frame[4]`` is the message type and ``frame[5]`` the first payload
byte. That matches the offsets used in the reverse-engineering notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

FLAG = 0x7E

PF_BROADCAST = 0xAF
PF_ADDRESSED = 0xBF

# Message types broadcast by Jacuzzi (unencrypted ProLink-style) spas
MSG_STATUS_UPDATE = 0x16
MSG_BUTTON_PRESS = 0x17
MSG_LIGHTS_UPDATE = 0x23

# Commands we send
MSG_SET_TIME = 0x18

# Bus address the ProLink module uses; commands are sent from it
PROLINK_CHANNEL = 0x0A

MAX_LEN = 128
MIN_FRAME_LEN = 7  # 7E LEN DST PF TYPE CRC 7E
MIN_STATUS_LEN = 28  # parse_status reads up to frame[27]
MIN_LIGHTS_LEN = 13  # parse_lights reads up to frame[10]

TSCALE_F = 0
TSCALE_C = 1


class ProtocolError(ValueError):
    """Raised when bytes do not form a valid frame."""


def crc(data: bytes) -> int:
    """Checksum over LEN..PAYLOAD (CRC-8, poly 0x07, init 0xB5, final xor 0x02)."""
    value = 0xB5
    for byte in data:
        for i in range(8):
            carry = value & 0x80
            value = ((value << 1) & 0xFF) | ((byte >> (7 - i)) & 0x01)
            if carry:
                value ^= 0x07
    for _ in range(8):
        carry = value & 0x80
        value = (value << 1) & 0xFF
        if carry:
            value ^= 0x07
    return value ^ 0x02


class Frame(NamedTuple):
    """A validated frame."""

    dst: int
    pf: int
    mtype: int
    payload: bytes
    raw: bytes  # the complete frame, including both 0x7E flags


def build_frame(dst: int, pf: int, mtype: int, payload: bytes = b"") -> bytes:
    """Build a complete frame, adding flags, length and CRC."""
    payload = bytes(payload)
    length = len(payload) + 5
    if length > MAX_LEN:
        raise ProtocolError("payload too long")
    body = bytes([length, dst, pf, mtype]) + payload
    return bytes([FLAG]) + body + bytes([crc(body), FLAG])


def build_set_datetime(
    year: int, month: int, day: int, hour: int, minute: int
) -> bytes:
    """Frame that sets the spa's date and clock (message type 0x18).

    Payload: month | 0xF0, day, year - 2000, hour, minute. The spa ignores
    the command unless the upper four bits of the month byte are all set.
    Jacuzzi controllers always run a 24-hour clock. Layout from pyjacuzzi
    and Jacuzzi-RS485, which decoded it from the ProLink app.
    """
    if not (2000 <= year <= 2255 and 1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError("date out of range")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time out of range")
    payload = bytes([month | 0xF0, day, year - 2000, hour, minute])
    return build_frame(PROLINK_CHANNEL, PF_ADDRESSED, MSG_SET_TIME, payload)


def parse_frame(raw: bytes) -> Frame:
    """Validate and split a complete frame. Raises ProtocolError if invalid."""
    raw = bytes(raw)
    if len(raw) < MIN_FRAME_LEN:
        raise ProtocolError("frame too short")
    if raw[0] != FLAG or raw[-1] != FLAG:
        raise ProtocolError("missing frame flag")
    if raw[1] + 2 != len(raw):
        raise ProtocolError("length byte does not match frame size")
    if crc(raw[1:-2]) != raw[-2]:
        raise ProtocolError("bad CRC")
    return Frame(dst=raw[2], pf=raw[3], mtype=raw[4], payload=raw[5:-2], raw=raw)


class FrameReader:
    """Split a byte stream into valid frames, resynchronising after garbage.

    Feed it whatever the socket returns (any chunking); it returns the frames
    completed by that chunk. Corrupt frames are dropped and counted in
    ``bad_frames`` rather than raising, since a noisy bus is normal.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self.bad_frames = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        frames: list[Frame] = []
        while True:
            start = self._buf.find(bytes([FLAG]))
            if start < 0:
                self._buf.clear()
                break
            if start > 0:
                del self._buf[:start]
            if len(self._buf) < 2:
                break
            length = self._buf[1]
            if length == FLAG:
                # Closing flag of a dropped frame followed by the next opener
                del self._buf[0]
                continue
            if length < MIN_FRAME_LEN - 2 or length > MAX_LEN:
                self.bad_frames += 1
                del self._buf[0]
                continue
            total = length + 2
            if len(self._buf) < total:
                break
            candidate = bytes(self._buf[:total])
            try:
                frames.append(parse_frame(candidate))
                del self._buf[:total]
            except ProtocolError:
                self.bad_frames += 1
                del self._buf[0]
        return frames


@dataclass(frozen=True)
class SpaStatus:
    """Decoded status update (message type 0x16)."""

    hour: int
    minute: int
    day_of_week: int  # 1 = Monday
    day: int
    month: int
    year: int
    filter2_mode: int
    heat_mode_state: int
    spa_state: int
    error_code: int
    temp_scale: int  # TSCALE_F or TSCALE_C
    current_temp: float | None  # None when the sensor reports 0xFF
    set_temp: float
    pump_states: tuple[int, int, int, int]  # index 0 = circulation, 1..3 = jets
    secondary_on: int
    primary_on: int
    blower_on: int
    uv_on: int
    flow_switch: int
    twelve_hour: bool
    setting_lock: int
    access_lock: int
    service_lock: int
    second_temp: float | None  # plumbing sensor, same scale as current_temp
    clearray_time: int
    water_time: int
    outer_filter_time: int | None
    inner_filter_time: int | None
    wifi_state: int | None


def parse_status(frame: bytes) -> SpaStatus:
    """Decode a complete 0x16 status frame (flags included).

    Field notes (offsets into the whole frame). Where a note says "believed"
    the meaning is a guess from the reverse-engineering work.

    =====  ==============================================================
    5, 6   hour, minute
    7      bits 7-5 day of week (1 = Monday), bits 4-0 day of month
    8, 9   month, year since 2000
    10     bits 7-6 secondary filter mode, 5-4 heat mode state,
           3-0 spa state
    11     error code (0 = none)
    12     current water temperature; 0xFF = no reading
    14     set temperature
    15     pump states, two bits each: 1-0 pump 0 (circulation), 3-2 pump 1,
           5-4 pump 2, 7-6 pump 3 (0 = off, 1 = low, 2 = high)
    16     two bits each: 7-6 secondary on, 5-4 primary on, 3-2 blower,
           1-0 UV (positions uncertain)
    17     believed to be the flow switch
    18     bit 0 temperature scale (1 = Celsius), bits 2-1 clear = 12 h clock
    20     bits 5-4 setting lock, 3-2 access lock, 1-0 service lock
    21     second water temperature (sensor in the plumbing)
    24, 25 ClearRay time; 26, 27 water time (big-endian)
    28-31  outer and inner filter times (only when LEN allows)
    32     bits 7-4 wifi state
    =====  ==============================================================

    Celsius temperatures are sent in half-degrees, Fahrenheit in whole degrees
    (confirmed on a J-480: 0x25 = 18.5 C, matching the topside panel). The
    meaning of byte 21 is unconfirmed: that J-480 sent 0x44 there (34 C).
    """
    d = bytes(frame)
    if len(d) < MIN_STATUS_LEN:
        raise ProtocolError("status frame too short")
    if d[4] != MSG_STATUS_UPDATE:
        raise ProtocolError("not a status update")

    temp_scale = TSCALE_C if d[18] & 0x01 else TSCALE_F
    divisor = 2 if temp_scale == TSCALE_C else 1

    def temp(raw: int) -> float | None:
        return None if raw == 0xFF else raw / divisor

    length = d[1]
    return SpaStatus(
        hour=d[5],
        minute=d[6],
        day_of_week=(d[7] & 0xE0) >> 5,
        day=d[7] & 0x1F,
        month=d[8],
        year=d[9] + 2000,
        filter2_mode=(d[10] & 0xC0) >> 6,
        heat_mode_state=(d[10] & 0x30) >> 4,
        spa_state=d[10] & 0x0F,
        error_code=d[11],
        temp_scale=temp_scale,
        current_temp=temp(d[12]),
        set_temp=d[14] / divisor,
        pump_states=(
            d[15] & 0x03,
            (d[15] & 0x0C) >> 2,
            (d[15] & 0x30) >> 4,
            (d[15] & 0xC0) >> 6,
        ),
        secondary_on=(d[16] & 0xC0) >> 6,
        primary_on=(d[16] & 0x30) >> 4,
        blower_on=(d[16] & 0x0C) >> 2,
        uv_on=d[16] & 0x03,
        flow_switch=d[17],
        twelve_hour=(d[18] & 0x06) == 0,
        setting_lock=(d[20] & 0x30) >> 4,
        access_lock=(d[20] & 0x0C) >> 2,
        service_lock=d[20] & 0x03,
        second_temp=temp(d[21]),
        clearray_time=d[24] * 256 + d[25],
        water_time=d[26] * 256 + d[27],
        outer_filter_time=d[28] * 256 + d[29] if length >= 30 else None,
        inner_filter_time=d[30] * 256 + d[31] if length >= 32 else None,
        wifi_state=(d[32] & 0xF0) >> 4 if length >= 33 else None,
    )


@dataclass(frozen=True)
class LightStatus:
    """Decoded lights update (message type 0x23).

    Byte 5 colour/mode code, 7 brightness, 8-10 red, green, blue. Decoded on
    a J-235; other models are unconfirmed.
    """

    mode: int
    brightness: int
    red: int
    green: int
    blue: int


def parse_lights(frame: bytes) -> LightStatus:
    """Decode a complete 0x23 lights frame (flags included)."""
    d = bytes(frame)
    if len(d) < MIN_LIGHTS_LEN:
        raise ProtocolError("lights frame too short")
    if d[4] != MSG_LIGHTS_UPDATE:
        raise ProtocolError("not a lights update")
    return LightStatus(mode=d[5], brightness=d[7], red=d[8], green=d[9], blue=d[10])
