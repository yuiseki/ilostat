import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("publish", ROOT / "src" / "publish.py")
p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p)


def _tree(
    tmp_path, card="license: cc-by-4.0\nraw/2026-01-01/\nindicator/OLD_A.csv.gz", tamper=False
):
    d = tmp_path / "data"
    run = d / "raw" / "2026-01-01"
    (run / "indicator").mkdir(parents=True)
    (run / "listings").mkdir()
    (run / "listings" / "indicator_x.html").write_text("<html>")
    files = {}
    for name, last in (("indicator/NEW_A.csv.gz", "2026-01-01"), ("indicator/OLD_A.csv.gz", "2022-05-03"),
                       ("dic/cl.csv", None)):  # fmt: skip
        (run / name).parent.mkdir(exist_ok=True)
        (run / name).write_bytes(name.encode())
        files[name] = {"sha256": hashlib.sha256(name.encode()).hexdigest(), "bytes": len(name),
                       "listing_last_update": last}  # fmt: skip
    (run / "MANIFEST.json").write_text(json.dumps({"files": files}))
    if tamper:
        (run / "indicator/NEW_A.csv.gz").write_bytes(b"x")
    for f in ("LICENSE", "provenance.yaml"):
        (d / f).write_text("x")
    (d / "README.md").write_text(card)
    return d


def test_a_file_last_updated_before_the_cc_by_date_is_left_out(tmp_path):
    files, left = p.collect(_tree(tmp_path))
    assert left == ["indicator/OLD_A.csv.gz"]
    assert "raw/2026-01-01/indicator/NEW_A.csv.gz" in files
    assert "raw/2026-01-01/dic/cl.csv" in files
    assert "raw/2026-01-01/listings/indicator_x.html" in files


def test_the_card_must_say_which_file_is_left_out(tmp_path):
    with pytest.raises(SystemExit, match="left out"):
        p.collect(_tree(tmp_path, card="license: cc-by-4.0\nraw/2026-01-01/"))


def test_a_changed_file_stops_the_push(tmp_path):
    with pytest.raises(SystemExit, match="not the file in its manifest"):
        p.collect(_tree(tmp_path, tamper=True))
