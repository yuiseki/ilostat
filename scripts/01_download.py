#!/usr/bin/env python3
"""Fetch every ILOSTAT bulk-download indicator file (.csv.gz) and dictionary file.

The file lists are the two bulk-download listing pages:

    https://rplumber.ilo.org/files/website/bulk/indicator.html
    https://rplumber.ilo.org/files/website/bulk/dic.html

indicator.html links one .csv.gz per indicator and frequency, plus the three
table-of-contents CSVs (en/fr/es), which are taken too. dic.html links the
code lists as .csv. The ref_area.html listing is not taken: it is the same
data cut by country instead of by indicator.

The server overwrites these files in place every day and keeps no history, so
the version is the fetch date (UTC, YYYY-MM-DD). A run on a later day resumes
an existing version instead of starting a new one as long as the listing's
Last-Modified has not changed, i.e. the source has not been regenerated.

Layout:

    data/raw/<YYYY-MM-DD>/indicator/<id>.csv.gz
    data/raw/<YYYY-MM-DD>/indicator/table_of_contents_<lang>.csv
    data/raw/<YYYY-MM-DD>/dic/<name>.csv
    data/raw/<YYYY-MM-DD>/listings/<kind>_<Last-Modified>.html   (each listing used)
    data/raw/<YYYY-MM-DD>/MANIFEST.json

Files are generated on request and sent without Content-Length (and without
Last-Modified), so each download is checked by reading it to the end with the
csv module (gzip decompressed to its end) and comparing the row count with the
n.records the listing states. The listing is a once-a-day snapshot (regenerated
around 21:00 UTC) while the files are built from the live database, so on a
mismatch the English table of contents, which follows the database, is fetched
again and its n.records is accepted too; the entry records both counts. An empty
or short response is a failure. A failed file is retried once after all others,
then recorded under "failed" in the manifest. A file already in the manifest
whose sha256 still matches is not fetched again; it keeps the listing it was
checked against (listing_last_modified), and every listing used is kept under
listings/. Every dictionary link named *.par answered HTTP 500 when this was
written; those end up under "failed".

    uv run python scripts/01_download.py
"""

import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import count_rows, sha256  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
BULK = "https://rplumber.ilo.org/files/website/bulk/"
LISTINGS = {"indicator": BULK + "indicator.html", "dic": BULK + "dic.html"}
# The listing pages answer an empty 200 to some clients without a browser
# User-Agent; this one was accepted when tested, so it is kept.
UA = "ilostat/1 (+https://github.com/yuiseki/ilostat)"
SIZE_LIMIT = 8 * 1000**3
# Measured .csv.gz sizes were 7.0-8.8 bytes per record; used for a pre-check only.
BYTES_PER_RECORD = 9
MIN_INTERVAL = 1.0
TOC_URL = "https://rplumber.ilo.org/metadata/toc/indicator?lang=en&format=.csv"
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


class _ListingParser(HTMLParser):
    """Collects the text and first link of every table cell, row by row."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict]] = []
        self.text: list[str] = []
        self._row: list[dict] | None = None
        self._cell: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = {"text": "", "href": None}
        elif tag == "a" and self._cell is not None and self._cell["href"] is None:
            self._cell["href"] = (dict(attrs).get("href") or "").strip()

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._cell["text"] = self._cell["text"].strip()
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        self.text.append(data)
        if self._cell is not None:
            self._cell["text"] += data


def _int_or_none(s: str) -> int | None:
    s = s.strip().replace(",", "")
    return int(s) if s else None


def parse_listing(html: str) -> dict:
    """Parse a bulk listing page into {"last_update", "rows"}.

    Each row: name, url, last_update, n_records, n_ref_area (the last two are
    None where the page leaves them blank or has no such column).
    """
    p = _ListingParser()
    p.feed(html)
    m = re.search(r"Last update:\s*(\d{4}-\d{2}-\d{2})", "".join(p.text))
    rows = []
    for cells in p.rows:
        if not cells or not cells[0]["href"]:
            continue
        url = cells[0]["href"]
        if not url.startswith("https://rplumber.ilo.org/") or "format=" not in url:
            continue  # "Up one level" and anything else that is not a file
        indicator_page = len(cells) >= 4 and re.fullmatch(r"[\d,]*", cells[2]["text"]) is not None
        rows.append(
            {
                "name": cells[0]["text"],
                "url": url,
                "last_update": cells[1]["text"] if len(cells) > 1 else "",
                "n_records": _int_or_none(cells[2]["text"]) if indicator_page else None,
                "n_ref_area": _int_or_none(cells[3]["text"]) if indicator_page else None,
            }
        )
    return {"last_update": m.group(1) if m else None, "rows": rows}


def file_name(name: str, url: str) -> str:
    """Local file name: the listed name plus the format the link asks for."""
    if not SAFE_NAME.fullmatch(name) or name.startswith("."):
        raise ValueError(f"unsafe file name {name!r}")
    fmt = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("format", [""])[0]
    if not re.fullmatch(r"(\.[a-z0-9]+)+", fmt):
        raise ValueError(f"no format in {url}")
    return name + fmt


def choose_version(raw: Path, today: str, listing_last_modified: str) -> str:
    """Resume the version whose listing had the same Last-Modified, else today."""
    if raw.exists() and listing_last_modified:
        for d in sorted(raw.iterdir(), reverse=True):
            mpath = d / "MANIFEST.json"
            if not mpath.is_file():
                continue
            m = json.loads(mpath.read_text())
            seen = [m.get("listings", {}).get("indicator", {})] + m.get("listing_history", [])
            if any(
                h.get("kind", "indicator") == "indicator"
                and h.get("last_modified") == listing_last_modified
                for h in seen
            ):
                return d.name
    return today


def toc_records(text: str) -> dict[str, int]:
    """id -> n.records from an indicator table of contents CSV."""
    rows = csv.DictReader(io.StringIO(text.lstrip("\ufeff"), newline=""))
    return {r["id"]: int(r["n.records"]) for r in rows if r["n.records"]}


def stamp(http_date: str) -> str:
    """'Sat, 03 Oct 2026 21:01:05 GMT' -> '20261003T210105Z'."""
    return parsedate_to_datetime(http_date).strftime("%Y%m%dT%H%M%SZ")


def row_count_problem(rows: int, listing_n: int | None, toc_n: int | None) -> str | None:
    """None when the rows match a count the source states, else the reason.

    The listing page is regenerated once a day, but the files are built from the
    live database and the table of contents follows it, so a file revised since
    the listing was written matches the live table of contents and not the listing.
    """
    stated = [n for n in (listing_n, toc_n) if n is not None]
    if not stated or rows in stated:
        return None
    return f"{rows} rows, the listing states n.records {listing_n}, the table of contents {toc_n}"


_last_request = 0.0


def _get(url: str):
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=600)


def get_listing(url: str) -> tuple[bytes, str]:
    with _get(url) as r:
        body = r.read()
        lm = r.headers.get("Last-Modified", "")
    if not body:
        raise SystemExit(f"{url}: empty response (the server does this for refused User-Agents)")
    return body, lm


def fetch(row: dict, dest: Path, live_toc=None) -> dict:
    """Download one file to dest, checked; raises on any problem."""
    tmp = dest.with_name(dest.name + ".part")
    try:
        with _get(row["url"]) as r, open(tmp, "wb") as f:
            while block := r.read(1 << 20):
                f.write(block)
            length = r.headers.get("Content-Length")
            lm = r.headers.get("Last-Modified", "")
            cd = r.headers.get("Content-Disposition", "")
        got = tmp.stat().st_size
        if got == 0:
            raise ValueError("empty response")
        if length is not None and got != int(length):
            raise ValueError(f"got {got} bytes, the server stated {length}")
        rows = count_rows(tmp, gz=dest.name.endswith(".gz"))
        toc_n = None
        problem = row_count_problem(rows, row["n_records"], None)
        if problem and live_toc is not None:
            toc_n = live_toc().get(row["name"])
            problem = row_count_problem(rows, row["n_records"], toc_n)
        if problem:
            raise ValueError(problem)
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    m = re.search(r'filename="?([^";]+)', cd)
    return {
        "url": row["url"],
        "bytes": got,
        "sha256": sha256(dest),
        "last_modified": lm,
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "served_name": m.group(1) if m else "",
        "rows": rows,
        "listing_last_update": row["last_update"],
        "n_records": row["n_records"],
        "n_ref_area": row["n_ref_area"],
        "toc_n_records": toc_n,
    }


def main() -> int:
    pages = {}
    for kind, url in LISTINGS.items():
        body, lm = get_listing(url)
        page = parse_listing(body.decode("cp1252"))
        if not page["rows"]:
            raise SystemExit(f"{url}: no files listed")
        pages[kind] = (body, lm, page)

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    version = choose_version(RAW, today, pages["indicator"][1])
    vdir = RAW / version
    mpath = vdir / "MANIFEST.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    manifest["version"] = version
    manifest.setdefault("files", {})
    manifest["failed"] = {}
    old = manifest.get("listings", {})
    for key, e in manifest["files"].items():
        # entries from before a listing change keep the listing they were checked against
        e.setdefault("listing_last_modified", old.get(key.split("/")[0], {}).get("last_modified"))
    history = manifest.setdefault("listing_history", [])
    for kind, info in old.items():
        if info.get("last_modified") and all(
            h["last_modified"] != info["last_modified"] for h in history if h["kind"] == kind
        ):
            saved = f"listings/{kind}_{stamp(info['last_modified'])}.html"
            history.append({**info, "kind": kind, "saved_as": saved})
    manifest["listings"] = {}
    for kind, (body, lm, page) in pages.items():
        (vdir / kind).mkdir(parents=True, exist_ok=True)
        saved = f"listings/{kind}_{stamp(lm)}.html"
        (vdir / saved).parent.mkdir(exist_ok=True)
        (vdir / saved).write_bytes(body)
        info = {
            "kind": kind,
            "url": LISTINGS[kind],
            "last_modified": lm,
            "last_update": page["last_update"],
            "files": len(page["rows"]),
            "n_records_total": sum(r["n_records"] or 0 for r in page["rows"]),
            "saved_as": saved,
        }
        manifest["listings"][kind] = info
        if all(h["last_modified"] != lm for h in history if h["kind"] == kind):
            history.append(info)

    def save():
        mpath.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")

    todo = []
    for kind, (_, _, page) in pages.items():
        for row in page["rows"]:
            todo.append((f"{kind}/{file_name(row['name'], row['url'])}", row))

    estimate = sum(r["n_records"] or 0 for _, r in todo) * BYTES_PER_RECORD
    print(f"version {version}: {len(todo)} files listed, estimated {estimate / 1e9:.1f} GB")
    if estimate > SIZE_LIMIT:
        raise SystemExit(f"estimated size exceeds the {SIZE_LIMIT / 1e9:.0f} GB limit; stopping")

    def total_bytes() -> int:
        return sum(e["bytes"] for e in manifest["files"].values())

    def live_toc() -> dict[str, int]:
        with _get(TOC_URL) as r:
            return toc_records(r.read().decode("utf-8"))

    skipped = fetched = 0
    retry = []
    for attempt in (1, 2):
        queue, retry = (todo, []) if attempt == 1 else (retry, [])
        if attempt == 2 and queue:
            print(f"retrying {len(queue)} failed file(s)")
        for key, row in queue:
            dest = vdir / key
            entry = manifest["files"].get(key)
            if (
                attempt == 1
                and entry
                and entry["url"] == row["url"]
                and dest.exists()
                and sha256(dest) == entry["sha256"]
            ):
                skipped += 1
                continue
            if total_bytes() > SIZE_LIMIT:
                save()
                raise SystemExit(f"{total_bytes():,} bytes on disk exceed the limit; stopping")
            try:
                manifest["files"][key] = fetch(row, dest, live_toc)
                manifest["files"][key]["listing_last_modified"] = manifest["listings"][
                    key.split("/")[0]
                ]["last_modified"]
            except Exception as e:  # noqa: BLE001 - any failure is retried, then recorded
                print(f"FAIL {key}: {e}")
                retry.append((key, row))
                manifest["files"].pop(key, None)
                continue
            fetched += 1
            e = manifest["files"][key]
            print(f"{key}: {e['bytes']:,} bytes, {e['rows']:,} rows")
            save()
    for key, row in retry:
        manifest["failed"][key] = {"url": row["url"], "n_records": row["n_records"]}
    save()
    print(
        f"done: {fetched} fetched, {skipped} already present, {len(retry)} failed, "
        f"{len(manifest['files'])} files, {total_bytes():,} bytes"
    )
    return 1 if retry else 0


if __name__ == "__main__":
    sys.exit(main())
