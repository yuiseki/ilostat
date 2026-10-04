# ilostat

A reproducible copy of the ILOSTAT bulk download: the labour statistics database of the
International Labour Organization (ILO). Every indicator file in `.csv.gz` (one per indicator
and frequency: annual, quarterly or monthly), the three indicator tables of contents (en/fr/es),
and the dictionary (code list) files.

## Source

- Bulk download facility: <https://ilostat.ilo.org/data/bulk/>
- Listings the script reads:
  - <https://rplumber.ilo.org/files/website/bulk/indicator.html>
  - <https://rplumber.ilo.org/files/website/bulk/dic.html>

The by-country listing (`ref_area.html`) is not taken: it holds the same records cut by
reference area instead of by indicator.

The server regenerates the files every day and keeps no earlier versions. Files are built on
request from the live database and sent without `Content-Length` or `Last-Modified`, so each
download is checked by reading it to the end and comparing its row count with the `n.records`
the listing states. The listing is regenerated once a day (around 21:00 UTC) and can lag the
files; on a mismatch the English table of contents is fetched again and its `n.records` is
accepted too. A version therefore holds each file as served at its `fetched_at`, which the
manifest records together with the listing it was checked against.

All dictionary links whose names end in `.par` returned HTTP 500 when this was written; they
are recorded under `failed` in the manifest.

## Licence

ILO databases and datasets published on or after 3 May 2023 are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); cite the ILO as the source
([ILO rights and permissions](https://www.ilo.org/rights-and-permissions)). Datasets produced
before that date do not automatically fall under CC BY 4.0, and a few files in the listing carry a
`last.update` earlier than 3 May 2023; the ILO name and emblem may not be used without permission.

## How to run

```sh
uv run python scripts/01_download.py   # fetch into data/raw/<YYYY-MM-DD>/
uv run python scripts/02_verify.py     # re-hash, read every file to the end, count rows
uv run python -m pytest
```

The version is the fetch date in UTC. A later run resumes the same version as long as the
listing's `Last-Modified` is unchanged; files already in the manifest with a matching sha256
are not fetched again. A file that fails is retried once at the end of the run and is then
recorded under `failed` in the manifest (the script exits non-zero).

## Layout

```
data/raw/<YYYY-MM-DD>/
  listings/<kind>_<Last-Modified>.html  every listing page a run used
  indicator/<id>.csv.gz               one file per indicator and frequency
  indicator/table_of_contents_<lang>.csv
  dic/<name>.csv                      code lists (<name>.par.csv: the variants the listing marks .par)
  MANIFEST.json                       per file: url, bytes, sha256, last_modified, fetched_at,
                                      served name, rows counted, the listing's last.update,
                                      n.records and n.ref_area, listing_last_modified, and
                                      toc_n_records when the table of contents was consulted
scripts/01_download.py, 02_verify.py, _common.py
tests/                                parsing tests with fixtures trimmed from the real listings
```
