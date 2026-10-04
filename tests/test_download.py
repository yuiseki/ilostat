import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), ROOT / "scripts" / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dl = load("01_download.py")
vf = load("02_verify.py")


def html(name: str) -> str:
    return (FIX / name).read_bytes().decode("cp1252")


def test_indicator_listing_rows():
    page = dl.parse_listing(html("indicator.html"))
    assert page["last_update"] == "2026-10-03"
    names = [r["name"] for r in page["rows"]]
    # the "Up one level" link is not a file
    assert names == [
        "table_of_contents_en",
        "table_of_contents_fr",
        "table_of_contents_es",
        "SDG_0111_SEX_AGE_RT_A",
        "INJ_WORK_SEX_MIG_NB_A",
    ]
    last = page["rows"][-1]
    # the href has a leading space in the page; it is stripped
    assert (
        last["url"]
        == "https://rplumber.ilo.org/data/indicator?id=INJ_WORK_SEX_MIG_NB_A&format=.csv.gz"
    )
    assert last["last_update"] == "2026-07-01"
    assert last["n_records"] == 4436
    assert last["n_ref_area"] == 117
    toc = page["rows"][0]
    assert toc["url"] == "https://rplumber.ilo.org/metadata/toc/indicator?lang=en&format=.csv"
    assert toc["n_records"] is None
    assert toc["n_ref_area"] is None


def test_dic_listing_rows():
    page = dl.parse_listing(html("dic.html"))
    assert page["last_update"] == "2026-10-03"
    assert [r["name"] for r in page["rows"]] == [
        "cl_age.par",
        "cl_age",
        "cl_age_en.par",
        "cl_age_en",
        "subject_fr",
    ]
    r = page["rows"][3]
    assert r["url"] == "https://rplumber.ilo.org/metadata/dic?var=cl_age&lang=en&format=.csv"
    assert r["last_update"] == "2026-10-03"
    assert r["n_records"] is None


def test_file_name_uses_the_format_in_the_url():
    assert (
        dl.file_name("X_A", "https://rplumber.ilo.org/data/indicator?id=X_A&format=.csv.gz")
        == "X_A.csv.gz"
    )
    assert (
        dl.file_name(
            "cl_age.par", "https://rplumber.ilo.org/metadata/dic?var=cl_age.par&format=.csv"
        )
        == "cl_age.par.csv"
    )
    with pytest.raises(ValueError):
        dl.file_name("../x", "https://rplumber.ilo.org/data/indicator?id=x&format=.csv.gz")
    with pytest.raises(ValueError):
        dl.file_name("x", "https://rplumber.ilo.org/data/indicator?id=x")


def test_choose_version_new_day(tmp_path):
    assert (
        dl.choose_version(tmp_path, "2026-10-05", "Sat, 03 Oct 2026 21:01:05 GMT") == "2026-10-05"
    )


def test_choose_version_resumes_same_listing(tmp_path):
    d = tmp_path / "2026-10-04"
    d.mkdir()
    (d / "MANIFEST.json").write_text(
        json.dumps({"listings": {"indicator": {"last_modified": "Sat, 03 Oct 2026 21:01:05 GMT"}}})
    )
    # a later day, but the source has not been regenerated: keep filling the same version
    assert (
        dl.choose_version(tmp_path, "2026-10-05", "Sat, 03 Oct 2026 21:01:05 GMT") == "2026-10-04"
    )
    # the source was regenerated: a new version
    assert (
        dl.choose_version(tmp_path, "2026-10-05", "Sun, 04 Oct 2026 21:01:05 GMT") == "2026-10-05"
    )


def test_count_rows_gzip_and_plain(tmp_path):
    assert vf.count_rows(FIX / "sample.csv.gz") == 5
    p = tmp_path / "a.csv"
    p.write_bytes('\ufeff"classif","label"\n"A","x, y"\n"B","multi\nline"\n'.encode())
    assert vf.count_rows(p) == 2


def test_count_rows_truncated_gzip_fails(tmp_path):
    data = (FIX / "sample.csv.gz").read_bytes()
    p = tmp_path / "t.csv.gz"
    p.write_bytes(data[:-10])
    with pytest.raises(EOFError):
        vf.count_rows(p)


def test_count_rows_part_file_named_by_caller(tmp_path):
    p = tmp_path / "x.csv.gz.part"
    p.write_bytes((FIX / "sample.csv.gz").read_bytes())
    assert vf.count_rows(p, gz=True) == 5


def test_toc_records():
    toc = dl.toc_records((FIX / "table_of_contents_en.csv").read_text(encoding="utf-8"))
    assert toc == {"EAR_INEE_CUR_NB_A": 11332, "INJ_WORK_SEX_MIG_NB_A": 4436}


def test_row_count_check_accepts_listing_or_toc():
    # the listing page is a daily snapshot; the files and the table of contents are newer
    assert dl.row_count_problem(11335, 11332, 11335) is None
    assert dl.row_count_problem(4436, 4436, None) is None
    assert dl.row_count_problem(10, None, None) is None
    assert "11332" in dl.row_count_problem(11000, 11332, 11335)


def test_stamp():
    assert dl.stamp("Sat, 03 Oct 2026 21:01:05 GMT") == "20261003T210105Z"


def test_choose_version_finds_an_earlier_listing_in_the_history(tmp_path):
    d = tmp_path / "2026-10-04"
    d.mkdir()
    lm_old, lm_new = "Sat, 03 Oct 2026 21:01:05 GMT", "Sun, 04 Oct 2026 21:02:44 GMT"
    (d / "MANIFEST.json").write_text(
        json.dumps(
            {
                "listings": {"indicator": {"last_modified": lm_new}},
                "listing_history": [{"kind": "indicator", "last_modified": lm_old}],
            }
        )
    )
    assert dl.choose_version(tmp_path, "2026-10-06", lm_old) == "2026-10-04"
