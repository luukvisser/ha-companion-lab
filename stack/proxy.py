"""A plain TCP pass-through: the one way into the internal network from 127.0.0.1.

The test HA runs only on the stack's internal network (no internet, no production network). This
proxy sits on both that network and an edge network, so the emulator (10.0.2.2 = this machine's
loopback) and the lab tools reach HA without HA itself being on a routed network.

  proxy.py <listen port> <target host> <target port>
"""
import asyncio
import sys

LISTEN, HOST, PORT = int(sys.argv[1]), sys.argv[2], int(sys.argv[3])


async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        writer.close()


async def handle(client_r: asyncio.StreamReader, client_w: asyncio.StreamWriter) -> None:
    try:
        target_r, target_w = await asyncio.open_connection(HOST, PORT)
    except OSError:
        client_w.close()
        return
    await asyncio.gather(pipe(client_r, target_w), pipe(target_r, client_w))


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", LISTEN)
    print(f"proxy :{LISTEN} -> {HOST}:{PORT}", flush=True)
    async with server:
        await server.serve_forever()


asyncio.run(main())
