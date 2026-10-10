#!/usr/bin/env python3
"""Write data/README.md (the Hub card), data/LICENSE and data/provenance.yaml.

Counts come from the manifest of the newest run under data/raw/.

    uv run python scripts/03_card.py
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CC = "https://creativecommons.org/licenses/by/4.0/"
RIGHTS = "https://www.ilo.org/rights-and-permissions"

_spec = importlib.util.spec_from_file_location("publish", ROOT / "src" / "publish.py")
pub = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pub)


def run_facts() -> dict:
    d = pub.current_run(DATA)
    m = json.loads((d / "MANIFEST.json").read_text())
    files = m["files"]
    out = {k: v for k, v in files.items() if pub.predates(v)}
    kept = {k: v for k, v in files.items() if k not in out}
    listings = {x["kind"]: x for x in m["listing_history"]}
    return {
        "run": d.name,
        "kept": kept,
        "out": out,
        "failed": m["failed"],
        "bytes": sum(v["bytes"] for v in kept.values()),
        "indicators": sum(
            k.startswith("indicator/") and "table_of_contents" not in k for k in kept
        ),
        "dics": sum(k.startswith("dic/") for k in kept),
        "records": listings["indicator"]["n_records_total"],
        "listing_date": listings["indicator"]["last_update"],
    }


def card(f: dict) -> str:
    out = "\n".join(
        f"- `{k}` (last.update {v['listing_last_update']}, {v['bytes']:,} bytes)"
        for k, v in f["out"].items()
    )
    return f"""---
license: cc-by-4.0
license_name: cc-by-4.0
license_link: {CC}
language:
- en
- fr
- es
task_categories:
- tabular-regression
- time-series-forecasting
tags:
- ilo
- ilostat
- labour
- employment
- unemployment
- wages
size_categories:
- 100M<n<1B
---

# ilostat

The ILOSTAT bulk download of the International Labour Organization (ILO): {f["indicators"]:,}
indicator files (one `.csv.gz` per indicator and frequency: annual, quarterly or monthly)
holding {f["records"]:,} records by the listing's count, the indicator tables of contents
(en, fr, es) and {f["dics"]} dictionary (code list) files, as the bulk facility served them on
{f["run"]}. The files are exactly as the ILO serves them; this dataset is a mirror, not a
reformatting.

Source: <https://ilostat.ilo.org/data/bulk/> (listings
<https://rplumber.ilo.org/files/website/bulk/indicator.html> and
<https://rplumber.ilo.org/files/website/bulk/dic.html>, kept under `raw/{f["run"]}/listings/`).

## The data follows upstream corrections

The server regenerates the files every day and keeps no earlier versions. This dataset
therefore holds one run, the newest, and is replaced as a whole when it is fetched again;
older runs are not kept here. The current run is `raw/{f["run"]}/`. Files are built on
request from the live database and sent without `Content-Length` or `Last-Modified`, so each
was checked by reading it to the end and comparing its row count with the `n.records` of the
listing (or of the table of contents, when the listing lags). `MANIFEST.json` gives for each
file its URL, size, sha256, fetch time, rows counted and the listing's `last.update`; the
listing used is dated {f["listing_date"]}.

## Layout

```
raw/{f["run"]}/MANIFEST.json
raw/{f["run"]}/listings/<kind>_<Last-Modified>.html   the listing pages the run used
raw/{f["run"]}/indicator/<id>.csv.gz                  one file per indicator and frequency
raw/{f["run"]}/indicator/table_of_contents_<lang>.csv
raw/{f["run"]}/dic/<name>.csv                         code lists
```

The dictionary variants whose names end in `.par` ({len(f["failed"])} links) answered HTTP 500
when they were fetched; they are listed under `failed` in the manifest and are not here.
The by-country listing (`ref_area`), which cuts the same records by reference area, is not
taken.

## Left out: files that predate the CC BY licence

The ILO licenses the databases and datasets it published on or after 3 May 2023 under CC BY
4.0 ({RIGHTS}) and says earlier ones do not automatically fall under it. An indicator file
whose `last.update` in the listing is earlier than 3 May 2023 is therefore not published
here (`MANIFEST.json` still lists it):

{out}

## Licence

CC BY 4.0 ({CC}); cite the ILO as the source ({RIGHTS}). The ILO name and emblem may not be
used without permission. Collection code: <https://github.com/yuiseki/ilostat> (MIT).
"""


def licence_file(f: dict) -> str:
    return f"""The contents of data/raw/ are ILOSTAT bulk downloads, © International Labour
Organization, unchanged.

Databases and datasets the ILO published on or after 3 May 2023 are licensed under CC BY 4.0
({CC}); cite the ILO as the source ({RIGHTS}). The ILO name and emblem may not be used
without permission. Datasets produced before 3 May 2023 do not automatically fall under CC
BY 4.0; the {len(f["out"])} indicator file(s) whose last.update is earlier are not included.

The code of the repository this dataset was built from is MIT licensed.
"""


def provenance(f: dict) -> str:
    out = "\n".join(f"    - {k}" for k in f["out"])
    return f"""# Where this data comes from and what was done to it.

source:
  name: ILOSTAT bulk download
  publisher: International Labour Organization (ILO)
  portal: https://ilostat.ilo.org/data/bulk/
  versions: none. The server regenerates daily; this dataset holds the newest run and follows upstream corrections.
  licence:
    applied: CC BY 4.0 ({CC}) for what the ILO published on or after 2023-05-03 ({RIGHTS})
    card: "license: cc-by-4.0"
    attribution_required: true
    left_out_because_last_update_before_2023_05_03:
{out}
  citation: >-
    International Labour Organization (ILO). ILOSTAT bulk download, https://ilostat.ilo.org/data/bulk/,
    accessed {f["run"]}. Licence: CC BY 4.0.

run:
  date: {f["run"]}
  indicator_files_published: {f["indicators"]}
  dictionary_files_published: {f["dics"]}
  files_left_out: {len(f["out"])}
  failed_downloads: {len(f["failed"])}  # the .par dictionary variants, HTTP 500

processing:
  - none: the files are as served, each read to the end and its rows counted against the listing
"""


def main() -> int:
    f = run_facts()
    (DATA / "README.md").write_text(card(f), encoding="utf-8")
    (DATA / "LICENSE").write_text(licence_file(f), encoding="utf-8")
    (DATA / "provenance.yaml").write_text(provenance(f), encoding="utf-8")
    print(f"{len(f['kept'])} files, {f['bytes']:,} bytes; left out {len(f['out'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
