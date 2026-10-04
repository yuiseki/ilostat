"""Helpers shared by 01_download.py and 02_verify.py."""

import csv
import gzip
import hashlib
import io
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def count_rows(path: Path, gz: bool | None = None) -> int:
    """Data rows of a CSV (header excluded), read with the csv module.

    A .gz file is decompressed to its end, so a truncated gzip raises EOFError
    and a corrupt one raises gzip.BadGzipFile or zlib.error. gz defaults to
    whether the name ends in .gz (pass it for a .part file).
    """
    if gz is None:
        gz = path.name.endswith(".gz")
    opener = gzip.open if gz else open
    with opener(path, "rb") as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
        n = sum(1 for _ in csv.reader(text))
    return max(n - 1, 0)
