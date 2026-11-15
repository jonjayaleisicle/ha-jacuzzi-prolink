"""Read-only asyncio client for a Jacuzzi ProLink WiFi module.

The ProLink module bridges the spa's RS-485 panel bus to a TCP socket on the
local network. Everything on the bus is forwarded to us; we only listen.
This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from collections.abc import Callable
from datetime import UTC, datetime
import logging

from .protocol import (
    MSG_LIGHTS_UPDATE,
    MSG_STATUS_UPDATE,
    Frame,
    FrameReader,
    LightStatus,
    ProtocolError,
    SpaStatus,
    parse_lights,
    parse_status,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 4257
CONNECT_TIMEOUT = 10.0
# The spa broadcasts several frames a second while awake. If the socket stays
# silent this long, assume the module dropped us and reconnect.
IDLE_TIMEOUT = 60.0
RECONNECT_MIN = 5.0
RECONNECT_MAX = 120.0
RECENT_FRAMES = 5


async def async_probe(host: str, port: int, timeout: float = CONNECT_TIMEOUT) -> None:
    """Open and close a TCP connection. Raises OSError/TimeoutError on failure."""
    _reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout
    )
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass


class ProLinkClient:
    """Keeps a connection to the module open and decodes what it hears."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        on_update: Callable[[], None] | None = None,
        *,
        idle_timeout: float = IDLE_TIMEOUT,
        reconnect_min: float = RECONNECT_MIN,
    ) -> None:
        self.host = host
        self.port = port
        self.on_update = on_update
        self._idle_timeout = idle_timeout
        self._reconnect_min = reconnect_min

        self.status: SpaStatus | None = None
        self.lights: LightStatus | None = None
        self.connected = False
        self.last_status_at: datetime | None = None

        # Diagnostics: what the bus is carrying, to help decode new models
        self.frame_counts: Counter[int] = Counter()
        self.recent_frames: dict[int, deque[str]] = {}
        self.bad_frames = 0
        self.connect_count = 0

        self._reader = FrameReader()
        self._last_raw: dict[int, bytes] = {}
        self._writer: asyncio.StreamWriter | None = None

    # -- lifecycle ---------------------------------------------------------

    async def run(self) -> None:
        """Connect, listen and reconnect forever. Cancel the task to stop."""
        backoff = self._reconnect_min
        while True:
            got_data = False
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), CONNECT_TIMEOUT
                )
            except (OSError, TimeoutError) as err:
                _LOGGER.debug("Cannot connect to %s:%s: %s", self.host, self.port, err)
            else:
                self._writer = writer
                self.connect_count += 1
                _LOGGER.debug("Connected to %s:%s", self.host, self.port)
                try:
                    got_data = await self._listen(reader)
                except (OSError, TimeoutError, ConnectionError) as err:
                    _LOGGER.debug("Connection to %s lost: %s", self.host, err)
                finally:
                    await self._close_writer()
            self._set_connected(False)
            backoff = self._reconnect_min if got_data else min(backoff * 2, RECONNECT_MAX)
            await asyncio.sleep(backoff)

    async def close(self) -> None:
        await self._close_writer()
        self._set_connected(False)

    async def _close_writer(self) -> None:
        writer, self._writer = self._writer, None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except OSError:
            pass

    # -- receiving ---------------------------------------------------------

    async def _listen(self, reader: asyncio.StreamReader) -> bool:
        """Read until the socket closes or goes idle. True if any frame arrived."""
        self._reader = FrameReader()
        got_frame = False
        while True:
            try:
                data = await asyncio.wait_for(reader.read(1024), self._idle_timeout)
            except TimeoutError:
                _LOGGER.debug("No data from %s for %ss", self.host, self._idle_timeout)
                return got_frame
            if not data:
                raise ConnectionError("connection closed by module")
            for frame in self._reader.feed(data):
                got_frame = True
                self.handle_frame(frame)
            self.bad_frames = self._reader.bad_frames

    def handle_frame(self, frame: Frame) -> None:
        """Process one validated frame. Public so tests can drive it directly."""
        mtype = frame.mtype
        self.frame_counts[mtype] += 1
        changed = not self.connected
        self.connected = True

        if self._last_raw.get(mtype) != frame.raw:
            self._last_raw[mtype] = frame.raw
            recent = self.recent_frames.setdefault(mtype, deque(maxlen=RECENT_FRAMES))
            recent.append(frame.raw.hex())
            try:
                if mtype == MSG_STATUS_UPDATE:
                    self.status = parse_status(frame.raw)
                    changed = True
                elif mtype == MSG_LIGHTS_UPDATE:
                    self.lights = parse_lights(frame.raw)
                    changed = True
            except ProtocolError as err:
                _LOGGER.debug("Ignoring frame %s: %s", frame.raw.hex(), err)

        if mtype == MSG_STATUS_UPDATE:
            self.last_status_at = datetime.now(UTC)
        if changed:
            self._notify()

    def _set_connected(self, connected: bool) -> None:
        if self.connected != connected:
            self.connected = connected
            self._notify()

    def _notify(self) -> None:
        if self.on_update is not None:
            self.on_update()

    def diagnostics(self) -> dict:
        return {
            "connected": self.connected,
            "connect_count": self.connect_count,
            "bad_frames": self.bad_frames,
            "last_status_at": self.last_status_at.isoformat()
            if self.last_status_at
            else None,
            "frame_counts": {f"0x{k:02x}": v for k, v in sorted(self.frame_counts.items())},
            "recent_frames": {
                f"0x{k:02x}": list(v) for k, v in sorted(self.recent_frames.items())
            },
        }
