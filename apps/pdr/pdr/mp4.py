"""Minimal MP4 sample-table reader, enough to pull a data track out intact.

ffmpeg's `-f data` muxer concatenates packet payloads with no separators, so
sample boundaries are lost and any framing that does not happen to be a whole
number of bytes per sample drifts. The PDR telemetry track needs exact sample
boundaries and real presentation timestamps, so this walks the container itself:
stsd/stts/stsz/stsc/stco give sizes, offsets and durations, and mdhd gives the
timescale that turns those durations into seconds.

Only the boxes needed for that walk are implemented.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

CONTAINER_BOXES = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"udta"}


@dataclass
class Sample:
    """One media sample: where it is, how big, and when it plays."""

    index: int
    offset: int
    size: int
    time: float


@dataclass
class Track:
    index: int
    handler: str
    codec_tag: str
    timescale: int
    samples: list[Sample]


def iter_boxes(fh: BinaryIO, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Yield (type, payload_start, payload_end) for boxes until `end`."""
    while fh.tell() < end - 7:
        start = fh.tell()
        header = fh.read(8)
        if len(header) < 8:
            return
        size, kind = struct.unpack(">I4s", header)
        if size == 1:
            size = struct.unpack(">Q", fh.read(8))[0]
            body = start + 16
        elif size == 0:
            size = end - start
            body = start + 8
        else:
            body = start + 8
        if size < 8:
            return
        yield kind, body, start + size
        fh.seek(start + size)


def find_boxes(fh: BinaryIO, end: int, path: list[bytes]) -> list[tuple[int, int]]:
    """Locate every box matching a nested path, returning payload extents."""
    found: list[tuple[int, int]] = []
    want, rest = path[0], path[1:]
    for kind, body, stop in iter_boxes(fh, end):
        if kind != want:
            continue
        if not rest:
            found.append((body, stop))
        else:
            here = fh.tell()
            fh.seek(body)
            found.extend(find_boxes(fh, stop, rest))
            fh.seek(here)
    return found


def read_table(fh: BinaryIO, start: int, fmt: str, fields: int) -> list[tuple]:
    """Read a standard full-box table: version/flags, count, then entries."""
    fh.seek(start)
    fh.read(4)  # version + flags
    count = struct.unpack(">I", fh.read(4))[0]
    size = struct.calcsize(fmt)
    raw = fh.read(count * size)
    return [struct.unpack_from(fmt, raw, i * size) for i in range(count)]


def read_tracks(path: Path) -> list[Track]:
    tracks: list[Track] = []
    with path.open("rb") as fh:
        fh.seek(0, 2)
        end = fh.tell()
        fh.seek(0)
        moov = find_boxes(fh, end, [b"moov"])
        if not moov:
            return []
        moov_start, moov_end = moov[0]
        fh.seek(moov_start)
        traks = find_boxes(fh, moov_end, [b"trak"])

        for i, (trak_start, trak_end) in enumerate(traks):
            fh.seek(trak_start)
            stbls = find_boxes(fh, trak_end, [b"mdia", b"minf", b"stbl"])
            fh.seek(trak_start)
            mdhds = find_boxes(fh, trak_end, [b"mdia", b"mdhd"])
            fh.seek(trak_start)
            hdlrs = find_boxes(fh, trak_end, [b"mdia", b"hdlr"])
            if not stbls or not mdhds:
                continue

            fh.seek(mdhds[0][0])
            version = fh.read(1)[0]
            fh.read(3)
            if version == 1:
                fh.read(16)
                timescale = struct.unpack(">I", fh.read(4))[0]
            else:
                fh.read(8)
                timescale = struct.unpack(">I", fh.read(4))[0]

            handler = ""
            if hdlrs:
                fh.seek(hdlrs[0][0] + 8)
                handler = fh.read(4).decode("latin-1")

            stbl_start, stbl_end = stbls[0]
            samples = read_samples(fh, stbl_start, stbl_end, timescale)
            codec_tag = read_codec_tag(fh, stbl_start, stbl_end)
            tracks.append(Track(i, handler, codec_tag, timescale, samples))
    return tracks


def read_codec_tag(fh: BinaryIO, stbl_start: int, stbl_end: int) -> str:
    fh.seek(stbl_start)
    stsd = find_boxes(fh, stbl_end, [b"stsd"])
    if not stsd:
        return ""
    # stsd payload: version+flags (4), entry_count (4), then entries.
    # Each entry starts with its own size (4) before the 4-byte format code.
    fh.seek(stsd[0][0] + 12)
    return fh.read(4).decode("latin-1", "replace")


def read_samples(fh: BinaryIO, stbl_start: int, stbl_end: int,
                 timescale: int) -> list[Sample]:
    def box(name: bytes) -> tuple[int, int] | None:
        fh.seek(stbl_start)
        got = find_boxes(fh, stbl_end, [name])
        return got[0] if got else None

    stsz_box, stsc_box = box(b"stsz"), box(b"stsc")
    stco_box, co64_box = box(b"stco"), box(b"co64")
    stts_box = box(b"stts")
    if not (stsz_box and stsc_box and stts_box and (stco_box or co64_box)):
        return []

    # sizes
    fh.seek(stsz_box[0])
    fh.read(4)
    uniform, count = struct.unpack(">II", fh.read(8))
    if uniform:
        sizes = [uniform] * count
    else:
        raw = fh.read(count * 4)
        sizes = list(struct.unpack(f">{count}I", raw))

    chunk_offsets = [
        c[0] for c in (
            read_table(fh, co64_box[0], ">Q", 1) if co64_box
            else read_table(fh, stco_box[0], ">I", 1)
        )
    ]
    stsc = read_table(fh, stsc_box[0], ">III", 3)
    stts = read_table(fh, stts_box[0], ">II", 2)

    # sample -> (chunk, offset within chunk)
    offsets: list[int] = []
    sample_i = 0
    for entry_i, (first_chunk, per_chunk, _) in enumerate(stsc):
        last_chunk = (
            stsc[entry_i + 1][0] - 1 if entry_i + 1 < len(stsc) else len(chunk_offsets)
        )
        for chunk in range(first_chunk, last_chunk + 1):
            if chunk - 1 >= len(chunk_offsets):
                break
            pos = chunk_offsets[chunk - 1]
            for _ in range(per_chunk):
                if sample_i >= len(sizes):
                    break
                offsets.append(pos)
                pos += sizes[sample_i]
                sample_i += 1

    # decode times
    times: list[float] = []
    t = 0
    for count_, delta in stts:
        for _ in range(count_):
            times.append(t / timescale)
            t += delta

    n = min(len(offsets), len(sizes), len(times))
    return [Sample(i, offsets[i], sizes[i], times[i]) for i in range(n)]


# The PDR's telemetry track declares handler 'ctbx', not the 'meta'/'data' a
# generic reader would look for.
TELEMETRY_HANDLERS = ("ctbx", "meta", "data")


def data_track(path: Path, codec_tag: str = "marl") -> Track | None:
    for t in read_tracks(path):
        if t.codec_tag == codec_tag or t.handler in TELEMETRY_HANDLERS:
            return t
    return None


def read_sample_bytes(path: Path, samples: list[Sample]) -> Iterator[tuple[Sample, bytes]]:
    with path.open("rb") as fh:
        for s in samples:
            fh.seek(s.offset)
            yield s, fh.read(s.size)
