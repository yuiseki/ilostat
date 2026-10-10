---
license: cc-by-4.0
license_name: cc-by-4.0
license_link: https://creativecommons.org/licenses/by/4.0/
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

The ILOSTAT bulk download of the International Labour Organization (ILO): 1,963
indicator files (one `.csv.gz` per indicator and frequency: annual, quarterly or monthly)
holding 399,233,347 records by the listing's count, the indicator tables of contents
(en, fr, es) and 244 dictionary (code list) files, as the bulk facility served them on
2026-10-04. The files are exactly as the ILO serves them; this dataset is a mirror, not a
reformatting.

Source: <https://ilostat.ilo.org/data/bulk/> (listings
<https://rplumber.ilo.org/files/website/bulk/indicator.html> and
<https://rplumber.ilo.org/files/website/bulk/dic.html>, kept under `raw/2026-10-04/listings/`).

## The data follows upstream corrections

The server regenerates the files every day and keeps no earlier versions. This dataset
therefore holds one run, the newest, and is replaced as a whole when it is fetched again;
older runs are not kept here. The current run is `raw/2026-10-04/`. Files are built on
request from the live database and sent without `Content-Length` or `Last-Modified`, so each
was checked by reading it to the end and comparing its row count with the `n.records` of the
listing (or of the table of contents, when the listing lags). `MANIFEST.json` gives for each
file its URL, size, sha256, fetch time, rows counted and the listing's `last.update`; the
listing used is dated 2026-10-04.

## Layout

```
raw/2026-10-04/MANIFEST.json
raw/2026-10-04/listings/<kind>_<Last-Modified>.html   the listing pages the run used
raw/2026-10-04/indicator/<id>.csv.gz                  one file per indicator and frequency
raw/2026-10-04/indicator/table_of_contents_<lang>.csv
raw/2026-10-04/dic/<name>.csv                         code lists
```

The dictionary variants whose names end in `.par` (244 links) answered HTTP 500
when they were fetched; they are listed under `failed` in the manifest and are not here.
The by-country listing (`ref_area`), which cuts the same records by reference area, is not
taken.

## Left out: files that predate the CC BY licence

The ILO licenses the databases and datasets it published on or after 3 May 2023 under CC BY
4.0 (https://www.ilo.org/rights-and-permissions) and says earlier ones do not automatically fall under it. An indicator file
whose `last.update` in the listing is earlier than 3 May 2023 is therefore not published
here (it is in the collection repository's manifest):

- `indicator/ILR_CBCT_NOC_RT_A.csv.gz` (last.update 2022-05-03, 5,140 bytes)

## Licence

CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); cite the ILO as the source (https://www.ilo.org/rights-and-permissions). The ILO name and emblem may not be
used without permission. Collection code: <https://github.com/yuiseki/ilostat> (MIT).
