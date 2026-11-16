"""Client against a fake ProLink module on localhost."""

import asyncio
import contextlib

import pytest

from custom_components.jacuzzi_prolink.client import ProLinkClient

from .frames import STATUS


async def _fake_module(frames: bytes):
    async def handle(reader, writer):
        writer.write(frames)
        await writer.drain()
        await reader.read()  # hold the connection open until the client closes
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_client_receives_status(socket_enabled):
    server, port = await _fake_module(STATUS + STATUS)  # duplicate is ignored
    updates = asyncio.Event()
    count = 0

    def on_update():
        nonlocal count
        count += 1
        updates.set()

    client = ProLinkClient("127.0.0.1", port, on_update)
    task = asyncio.create_task(client.run())
    try:
        await asyncio.wait_for(updates.wait(), 5)
        await asyncio.sleep(0.1)
        assert client.connected
        assert client.status.current_temp == 19.0
        assert client.frame_counts[0x16] == 2
        assert count == 1
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await client.close()
        server.close()
        await server.wait_closed()


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_client_reconnects_after_close(socket_enabled):
    connections = 0

    async def handle(reader, writer):
        nonlocal connections
        connections += 1
        writer.write(STATUS)
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = ProLinkClient("127.0.0.1", port, reconnect_min=0.05)
    task = asyncio.create_task(client.run())
    try:
        for _ in range(100):
            if connections >= 2:
                break
            await asyncio.sleep(0.05)
        assert connections >= 2
        assert client.status is not None
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await client.close()
        server.close()
        await server.wait_closed()


class FakeModule:
    """A ProLink module that streams status and reacts to set-temperature.

    ``behaviour`` lists, per connection, what the spa does with a command:
    "apply" (change and report it), "ignore" (nothing), or "stall" (apply it
    but stop reporting, like a connection the module has silently dropped).
    """

    def __init__(self, behaviour):
        self.behaviour = list(behaviour)
        self.connections = 0
        self.commands: list[bytes] = []
        self.set_raw = STATUS[14]
        self.server = None

    def status(self) -> bytes:
        from custom_components.jacuzzi_prolink import protocol as p

        raw = bytearray(STATUS)
        raw[14] = self.set_raw
        return p.build_frame(raw[2], raw[3], raw[4], bytes(raw[5:-2]))

    async def handle(self, reader, writer):
        from custom_components.jacuzzi_prolink import protocol as p

        mode = self.behaviour[min(self.connections, len(self.behaviour) - 1)]
        self.connections += 1
        frames = p.FrameReader()
        stalled = False

        async def stream():
            while not stalled:
                writer.write(self.status())
                await writer.drain()
                await asyncio.sleep(0.02)

        streamer = asyncio.create_task(stream())
        try:
            while data := await reader.read(1024):
                for frame in frames.feed(data):
                    self.commands.append(frame.raw)
                    if mode in ("apply", "stall"):
                        self.set_raw = frame.payload[0]
                    if mode == "stall":
                        stalled = True
        except ConnectionError:
            pass
        finally:
            streamer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await streamer
            writer.close()

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def __aexit__(self, *exc):
        self.server.close()
        await self.server.wait_closed()


async def _with_client(port, body):
    client = ProLinkClient(
        "127.0.0.1", port, reconnect_min=0.05, confirm_timeout=0.3, reconnect_wait=2
    )
    task = asyncio.create_task(client.run())
    try:
        await body(client)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await client.close()


def _set_temp(client, temp):
    from custom_components.jacuzzi_prolink.protocol import TSCALE_C, build_set_temperature

    return client.send_and_confirm(
        build_set_temperature(temp, TSCALE_C),
        lambda: client.status is not None and client.status.set_temp == temp,
    )


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_command_confirmed_first_time(socket_enabled):
    async with FakeModule(["apply"]) as port:

        async def body(client):
            await _set_temp(client, 20.5)
            assert client.status.set_temp == 20.5
            assert client.connect_count == 1

        await _with_client(port, body)


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_ignored_command_is_resent_after_reconnecting(socket_enabled):
    fake = FakeModule(["ignore", "apply"])
    async with fake as port:

        async def body(client):
            await _set_temp(client, 20.5)
            assert client.status.set_temp == 20.5

        await _with_client(port, body)
    assert fake.connections == 2
    assert len(fake.commands) == 2  # sent, ignored, reconnected, sent again


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_command_that_landed_is_not_resent(socket_enabled):
    # The spa applied the command but the connection went quiet before it
    # reported. After reconnecting the fresh status shows the change, so the
    # command must not be sent again (for a toggle that would undo it).
    fake = FakeModule(["stall", "apply"])
    async with fake as port:

        async def body(client):
            await _set_temp(client, 20.5)
            assert client.status.set_temp == 20.5
            assert any("confirmed after reconnecting" in e for e in client.sent_frames)

        await _with_client(port, body)
    assert len(fake.commands) == 1


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_command_never_confirmed_raises(socket_enabled):
    from custom_components.jacuzzi_prolink.client import CommandNotConfirmed

    fake = FakeModule(["ignore"])
    async with fake as port:

        async def body(client):
            with pytest.raises(CommandNotConfirmed):
                await _set_temp(client, 20.5)

        await _with_client(port, body)
    assert len(fake.commands) == 2


@pytest.mark.allow_hosts(["127.0.0.1"])
async def test_drops_are_counted_but_closing_is_not(socket_enabled):
    connections = 0

    async def handle(reader, writer):
        nonlocal connections
        connections += 1
        writer.write(STATUS)
        await writer.drain()
        if connections == 1:
            writer.close()  # the module drops us once
        else:
            await reader.read()
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    client = ProLinkClient("127.0.0.1", port, reconnect_min=0.05)
    task = asyncio.create_task(client.run())
    try:
        for _ in range(100):
            if connections >= 2 and client.connected:
                break
            await asyncio.sleep(0.05)
        assert client.drop_count == 1
        assert client.last_drop_at is not None
        assert client.last_reconnect_at >= client.last_drop_at
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await client.close()
        server.close()
        await server.wait_closed()
    assert client.drop_count == 1  # closing down is not a drop
