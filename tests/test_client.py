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
