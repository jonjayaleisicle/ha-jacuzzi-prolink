"""Protocol layer: pure functions, no Home Assistant needed."""

import pytest

from custom_components.jacuzzi_prolink import protocol as p

from .frames import J480_LIGHTS, J480_STATUS, MODULE_IDENT_REQ, SET_TEMP_20C, STATUS


@pytest.mark.parametrize(
    "raw", [STATUS, SET_TEMP_20C, MODULE_IDENT_REQ, J480_STATUS, J480_LIGHTS]
)
def test_real_frames_have_valid_crc(raw):
    frame = p.parse_frame(raw)
    assert p.build_frame(frame.dst, frame.pf, frame.mtype, frame.payload) == raw


def test_parse_status():
    s = p.parse_status(STATUS)
    assert (s.hour, s.minute) == (16, 18)
    assert (s.day_of_week, s.day, s.month, s.year) == (1, 7, 11, 2022)
    assert s.temp_scale == p.TSCALE_C
    assert s.current_temp == 19.0
    assert s.set_temp == 19.0
    assert s.pump_states == (2, 2, 0, 0)
    assert s.error_code == 0
    assert s.primary_on == 1
    assert (s.setting_lock, s.access_lock, s.service_lock) == (0, 0, 0)


def test_fahrenheit_and_missing_temperature():
    raw = bytearray(STATUS)
    raw[18] &= 0xFE  # Fahrenheit
    raw[12] = 0xFF  # no reading
    raw[14] = 101
    s = p.parse_status(bytes(raw))
    assert s.temp_scale == p.TSCALE_F
    assert s.current_temp is None
    assert s.set_temp == 101


def test_parse_status_rejects_other_types():
    with pytest.raises(p.ProtocolError):
        p.parse_status(SET_TEMP_20C)


def test_parse_lights():
    raw = p.build_frame(0xFF, p.PF_BROADCAST, p.MSG_LIGHTS_UPDATE, bytes([5, 0, 3, 10, 20, 30]))
    assert p.parse_lights(raw) == p.LightStatus(mode=5, brightness=3, red=10, green=20, blue=30)


def test_frame_reader_handles_chunks_and_garbage():
    reader = p.FrameReader()
    stream = b"\x00\x7e\x01junk" + STATUS + SET_TEMP_20C
    frames = []
    for i in range(0, len(stream), 3):  # deliver in awkward 3-byte chunks
        frames += reader.feed(stream[i : i + 3])
    assert [f.raw for f in frames] == [STATUS, SET_TEMP_20C]


def test_frame_reader_drops_bad_crc():
    reader = p.FrameReader()
    corrupt = bytearray(STATUS)
    corrupt[-2] ^= 0xFF
    assert reader.feed(bytes(corrupt) + SET_TEMP_20C) == [p.parse_frame(SET_TEMP_20C)]
    assert reader.bad_frames >= 1


def test_parse_j480_status():
    s = p.parse_status(J480_STATUS)
    assert s.temp_scale == p.TSCALE_C
    assert s.current_temp == 18.5
    assert s.set_temp == 18.5
    assert s.pump_states == (0, 0, 0, 0)
    assert s.error_code == 0
    assert not s.twelve_hour


def test_build_set_datetime():
    raw = p.build_set_datetime(2026, 11, 15, 21, 42)
    frame = p.parse_frame(raw)  # valid flags, length and CRC
    assert frame.dst == p.PROLINK_CHANNEL
    assert frame.pf == p.PF_ADDRESSED
    assert frame.mtype == p.MSG_SET_TIME
    # month | 0xF0, day, year - 2000, hour, minute
    assert frame.payload == bytes([0xFB, 15, 26, 21, 42])


@pytest.mark.parametrize(
    "args", [(1999, 1, 1, 0, 0), (2026, 13, 1, 0, 0), (2026, 1, 1, 24, 0), (2026, 1, 1, 0, 60)]
)
def test_build_set_datetime_rejects_bad_values(args):
    with pytest.raises(ValueError):
        p.build_set_datetime(*args)
