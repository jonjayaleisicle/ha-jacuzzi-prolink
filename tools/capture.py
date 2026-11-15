#!/usr/bin/env python3
"""Record what a ProLink module sends, to check and improve the decoding.

Needs only Python 3.10+ (no Home Assistant). Run it from a computer on the
same network as the spa:

    python3 tools/capture.py 192.168.1.50 --seconds 120 --out capture.txt

While it runs, note what the spa's topside panel shows (water temperature,
set point, which pumps are on) and press a few buttons, writing down the time
of each press. Every distinct frame is printed with a timestamp and saved to
the output file; status frames are also decoded.

It only listens; it never sends anything to the spa. If the integration is
already running in Home Assistant, disable it first in case the module only
accepts one connection at a time.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import time

sys.path.insert(
    0, str(pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "jacuzzi_prolink")
)
import protocol as p  # noqa: E402


async def capture(host: str, port: int, seconds: float, out: pathlib.Path) -> int:
    print(f"Connecting to {host}:{port} ...")
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 10)
    print(f"Connected. Recording for {seconds:.0f} s; press Ctrl+C to stop early.")
    frames = p.FrameReader()
    seen: dict[int, bytes] = {}
    counts: dict[int, int] = {}
    start = time.monotonic()
    with out.open("w") as fh:
        fh.write(f"# ProLink capture {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        try:
            while (left := seconds - (time.monotonic() - start)) > 0:
                try:
                    data = await asyncio.wait_for(reader.read(1024), min(left, 30))
                except TimeoutError:
                    print("  (no data for a while - is the spa asleep? press a button)")
                    continue
                if not data:
                    print("Module closed the connection.")
                    break
                for frame in frames.feed(data):
                    counts[frame.mtype] = counts.get(frame.mtype, 0) + 1
                    if seen.get(frame.mtype) == frame.raw:
                        continue
                    seen[frame.mtype] = frame.raw
                    stamp = time.strftime("%H:%M:%S")
                    line = f"{stamp} type=0x{frame.mtype:02x} {frame.raw.hex()}"
                    print(line)
                    fh.write(line + "\n")
                    if frame.mtype == p.MSG_STATUS_UPDATE:
                        try:
                            s = p.parse_status(frame.raw)
                        except p.ProtocolError as err:
                            print(f"    (could not decode: {err})")
                            continue
                        unit = "C" if s.temp_scale == p.TSCALE_C else "F"
                        print(
                            f"    water {s.current_temp}{unit} set {s.set_temp}{unit} "
                            f"pumps {s.pump_states} error {s.error_code} "
                            f"clock {s.hour:02d}:{s.minute:02d}"
                        )
        except KeyboardInterrupt:
            pass
        finally:
            writer.close()
        summary = ", ".join(f"0x{k:02x}: {v}" for k, v in sorted(counts.items()))
        fh.write(f"# frame counts {summary}; bad frames {frames.bad_frames}\n")
    print(f"\nFrame counts: {summary or 'none'}; bad frames: {frames.bad_frames}")
    print(f"Saved to {out}")
    return 0 if counts else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("host", help="IP address of the ProLink module")
    parser.add_argument("--port", type=int, default=4257)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("capture.txt"))
    args = parser.parse_args()
    try:
        return asyncio.run(capture(args.host, args.port, args.seconds, args.out))
    except (OSError, TimeoutError) as err:
        print(f"Could not connect: {err}")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
