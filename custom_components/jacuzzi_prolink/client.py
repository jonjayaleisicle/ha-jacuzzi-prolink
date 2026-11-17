"""Asyncio client for a Jacuzzi ProLink WiFi module.

The ProLink module bridges the spa's RS-485 panel bus to a TCP socket on the
local network. The spa's broadcasts are forwarded to us, and frames we write
are put on the bus by the module.
This module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
from collections import Counter, deque
from collections.abc import Callable
from datetime import UTC, datetime
import logging

from .protocol import (
    MSG_FILTER_CYCLE,
    MSG_LIGHTS_UPDATE,
    MSG_STATUS_UPDATE,
    PANEL_REQUEST_FILTER_CYCLE,
    FilterCycle,
    Frame,
    FrameReader,
    LightStatus,
    ProtocolError,
    SpaStatus,
    build_panel_request,
    parse_filter_cycle,
    parse_lights,
    parse_status,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 4257
CONNECT_TIMEOUT = 10.0
# The spa broadcasts several frames a second while awake. If the socket stays
# silent this long, assume the module dropped us and reconnect.
IDLE_TIMEOUT = 5.0
# The spa reports a change about a second after a command. Allow a margin.
CONFIRM_TIMEOUT = 4.0
# How long a command waits for a (re)connection and a fresh status report
RECONNECT_WAIT = 20.0
# The spa only sends its filter cycle settings when asked
FILTER_POLL_INTERVAL = 3600.0
RECONNECT_MIN = 1.0
# Short drops (the J-480's module drops about every 15 minutes and is back
# within seconds) do not make the spa unavailable unless they last this long
DROP_GRACE = 60.0
RECONNECT_MAX = 120.0
RECENT_FRAMES = 30
SENT_FRAMES = 30


def _stamp() -> str:
    """UTC time to the second, to line frames up with what happened."""
    return datetime.now(UTC).strftime("%H:%M:%S")


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


class CommandNotConfirmed(Exception):
    """The spa did not report the requested change, even after a retry."""


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
        confirm_timeout: float = CONFIRM_TIMEOUT,
        reconnect_wait: float = RECONNECT_WAIT,
        filter_poll_interval: float = FILTER_POLL_INTERVAL,
    ) -> None:
        self.host = host
        self.port = port
        self.on_update = on_update
        self._idle_timeout = idle_timeout
        self._reconnect_min = reconnect_min
        self._confirm_timeout = confirm_timeout
        self._reconnect_wait = reconnect_wait
        self._filter_poll_interval = filter_poll_interval
        self._next_filter_request = 0.0

        self.status: SpaStatus | None = None
        self.lights: LightStatus | None = None
        self.filter_cycle: FilterCycle | None = None
        self.filter_requests = 0
        self.filter_replies = 0
        self.connected = False
        self.last_status_at: datetime | None = None

        # Diagnostics: what the bus is carrying, to help decode new models
        self.frame_counts: Counter[int] = Counter()
        self.recent_frames: dict[int, deque[str]] = {}
        self.sent_frames: deque[str] = deque(maxlen=SENT_FRAMES)
        self.bad_frames = 0
        self.connect_count = 0
        # A drop is losing a connection that was delivering data
        self.drop_count = 0
        self.last_drop_at: datetime | None = None
        self.last_reconnect_at: datetime | None = None

        self._reader = FrameReader()
        self._last_raw: dict[int, bytes] = {}
        self._writer: asyncio.StreamWriter | None = None
        self._frame_event = asyncio.Event()  # set whenever a frame arrives
        self._reconnect_now = asyncio.Event()
        self._status_seq = 0  # counts every status frame, changed or not
        self._send_lock = asyncio.Lock()

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
            try:  # a command that needs the connection back cuts the wait short
                await asyncio.wait_for(self._reconnect_now.wait(), backoff)
            except TimeoutError:
                pass
            self._reconnect_now.clear()

    async def send(self, frame: bytes) -> None:
        """Write a command frame to the module.

        The ProLink module puts it on the spa's bus itself, so there is no
        channel negotiation or clear-to-send to wait for.
        """
        writer = self._writer
        if writer is None or not self.connected:
            raise ConnectionError("not connected to the ProLink module")
        _LOGGER.debug("Sending %s", frame.hex())
        writer.write(frame)
        await writer.drain()
        self._log_command(f"sent {frame.hex()}")

    async def send_and_confirm(
        self, frame: bytes, confirmed: Callable[[], bool], *, retries: int = 1
    ) -> None:
        """Send a command and wait for the spa's status to show it took effect.

        ``confirmed`` checks the decoded state. If it does not turn true in
        time, the connection is assumed stale (the module can drop us without
        closing the socket): reconnect, wait for a fresh status report, and
        resend only if the change still has not happened. That last check
        matters for toggles, where resending a press that did land would undo
        it. Raises ConnectionError if the spa cannot be reached, and
        CommandNotConfirmed if it never reports the change.
        """
        async with self._send_lock:
            for attempt in range(retries + 1):
                if attempt:
                    self._log_command("no confirmation; reconnecting")
                    await self._reconnect()
                    if not await self._wait_for_fresh_status():
                        raise ConnectionError("ProLink module did not reconnect")
                    if confirmed():
                        self._log_command("confirmed after reconnecting")
                        return
                elif not self.connected and not await self._wait_for_fresh_status():
                    raise ConnectionError("not connected to the ProLink module")
                try:
                    await self.send(frame)
                except (OSError, ConnectionError) as err:
                    self._log_command(f"send failed: {err}")
                    if attempt == retries:
                        raise
                    continue
                if await self._wait_for(confirmed, self._confirm_timeout):
                    self._log_command("confirmed")
                    return
            self._log_command("not confirmed; giving up")
            raise CommandNotConfirmed(frame.hex())

    async def _reconnect(self) -> None:
        await self._close_writer()
        self._set_connected(False)
        self._reconnect_now.set()

    async def _wait_for_fresh_status(self) -> bool:
        """Wait until connected and a status frame newer than now arrives."""
        seq = self._status_seq
        return await self._wait_for(
            lambda: self.connected and self._status_seq > seq, self._reconnect_wait
        )

    async def _wait_for(self, condition: Callable[[], bool], timeout: float) -> bool:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not condition():
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            self._frame_event.clear()
            try:
                await asyncio.wait_for(self._frame_event.wait(), remaining)
            except TimeoutError:
                return condition()
        return True

    def _log_command(self, message: str) -> None:
        self.sent_frames.append(f"{_stamp()} {message}")

    async def close(self) -> None:
        """Close for good (unload or shutdown); not counted as a drop."""
        await self._close_writer()
        if self.connected:
            self.connected = False
            self._notify()

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
        self._next_filter_request = 0.0  # ask again on every new connection
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
            if got_frame:
                await self._maybe_request_filter_cycle()

    async def _maybe_request_filter_cycle(self) -> None:
        """Ask for the filter cycle settings soon after connecting, then periodically."""
        loop = asyncio.get_running_loop()
        if loop.time() < self._next_filter_request or self._writer is None:
            return
        self._next_filter_request = loop.time() + self._filter_poll_interval
        self.filter_requests += 1
        self._writer.write(build_panel_request(PANEL_REQUEST_FILTER_CYCLE))
        await self._writer.drain()

    def handle_frame(self, frame: Frame) -> None:
        """Process one validated frame. Public so tests can drive it directly."""
        mtype = frame.mtype
        self.frame_counts[mtype] += 1
        changed = not self.connected
        if changed and self.drop_count:
            self.last_reconnect_at = datetime.now(UTC)
        self.connected = True

        if self._last_raw.get(mtype) != frame.raw:
            self._last_raw[mtype] = frame.raw
            recent = self.recent_frames.setdefault(mtype, deque(maxlen=RECENT_FRAMES))
            recent.append(f"{_stamp()} {frame.raw.hex()}")
            try:
                if mtype == MSG_STATUS_UPDATE:
                    self.status = parse_status(frame.raw)
                    changed = True
                elif mtype == MSG_LIGHTS_UPDATE:
                    self.lights = parse_lights(frame.raw)
                    changed = True
                elif mtype == MSG_FILTER_CYCLE:
                    self.filter_cycle = parse_filter_cycle(frame.raw)
                    changed = True
            except ProtocolError as err:
                _LOGGER.debug("Ignoring frame %s: %s", frame.raw.hex(), err)

        if mtype == MSG_FILTER_CYCLE:
            self.filter_replies += 1
        if mtype == MSG_STATUS_UPDATE:
            self.last_status_at = datetime.now(UTC)
            self._status_seq += 1
        if changed:
            self._notify()
        self._frame_event.set()

    @property
    def available(self) -> bool:
        """Connected, or dropped less than DROP_GRACE seconds ago."""
        if self.connected:
            return True
        if self.last_drop_at is None:
            return False
        return (datetime.now(UTC) - self.last_drop_at).total_seconds() < DROP_GRACE

    def _set_connected(self, connected: bool) -> None:
        if self.connected != connected:
            if not connected:
                self.drop_count += 1
                self.last_drop_at = datetime.now(UTC)
            self.connected = connected
            self._notify()

    def _notify(self) -> None:
        if self.on_update is not None:
            self.on_update()

    def diagnostics(self) -> dict:
        return {
            "connected": self.connected,
            "connect_count": self.connect_count,
            "drop_count": self.drop_count,
            "filter_requests": self.filter_requests,
            "filter_replies": self.filter_replies,
            "last_drop_at": self.last_drop_at.isoformat() if self.last_drop_at else None,
            "last_reconnect_at": self.last_reconnect_at.isoformat()
            if self.last_reconnect_at
            else None,
            "bad_frames": self.bad_frames,
            "last_status_at": self.last_status_at.isoformat()
            if self.last_status_at
            else None,
            "frame_counts": {f"0x{k:02x}": v for k, v in sorted(self.frame_counts.items())},
            "sent_frames": list(self.sent_frames),
            "recent_frames": {
                f"0x{k:02x}": list(v) for k, v in sorted(self.recent_frames.items())
            },
        }
