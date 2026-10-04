#!/usr/bin/env python3
"""Check every version under data/raw/ against its MANIFEST.json.

For each file in the manifest:
  - it exists, with the bytes and sha256 recorded
  - it reads to the end with the csv module (a .gz decompressed to its end)
  - its data rows equal the rows recorded, and equal the n.records stated by
    the listing page or by the table of contents (the listing is a daily
    snapshot; the files and the table of contents follow the live database)
Files the download recorded as failed are reported as FAIL too. Prints one
ok/FAIL line per check and exits non-zero on any failure.

    uv run python scripts/02_verify.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import count_rows, sha256  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def main() -> int:
    failures = []

    def check(ok: bool, what: str) -> None:
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            failures.append(what)

    manifests = sorted(RAW.glob("*/MANIFEST.json"))
    check(bool(manifests), f"a MANIFEST.json under {RAW}")
    for mpath in manifests:
        d = mpath.parent
        m = json.loads(mpath.read_text())
        files = m.get("files", {})
        for kind, listing in m.get("listings", {}).items():
            n = sum(1 for k in files if k.startswith(kind + "/"))
            check(n == listing["files"], f"{d.name}/{kind}: {n} of {listing['files']} listed files")
        for key, e in sorted(files.items()):
            p = d / key
            name = f"{d.name}/{key}"
            if not p.is_file():
                check(False, f"{name}: missing")
                continue
            size = p.stat().st_size
            check(size == e["bytes"], f"{name}: {size:,} bytes")
            check(sha256(p) == e["sha256"], f"{name}: sha256")
            try:
                rows = count_rows(p)
            except Exception as ex:  # noqa: BLE001 - any read error is a failure
                check(False, f"{name}: unreadable ({type(ex).__name__}: {ex})")
                continue
            check(rows == e["rows"], f"{name}: {rows:,} rows")
            stated = [e.get(k) for k in ("n_records", "toc_n_records") if e.get(k) is not None]
            if stated:
                check(rows in stated, f"{name}: rows match a stated n.records {stated}")
        for key in sorted(m.get("failed", {})):
            check(False, f"{d.name}/{key}: recorded as failed by the download")
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
