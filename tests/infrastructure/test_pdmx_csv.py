from __future__ import annotations

import pytest
from infrastructure.importers.pdmx_csv import read_pdmx_csv


def _write(tmp_path, content: str) -> str:
    path = tmp_path / "pdmx.csv"
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_read_pdmx_csv_detects_columns(tmp_path):
    csv_path = _write(
        tmp_path,
        "relative_path,archive,url,key\n"
        "mxl/4/5/8/000458.mxl,pdmx-mxl-01.tar.gz,http://src/1.tar.gz,K618\n"
        "mxl/4/5/9/000459.mxl,pdmx-mxl-01.tar.gz,http://src/1.tar.gz,\n",
    )
    rows = list(read_pdmx_csv(csv_path))
    assert len(rows) == 2
    assert rows[0].relative_path == "mxl/4/5/8/000458.mxl"
    assert rows[0].archive_name == "pdmx-mxl-01.tar.gz"
    assert rows[0].archive_url == "http://src/1.tar.gz"
    assert rows[0].logical_id == "K618"
    assert rows[1].logical_id is None


def test_read_pdmx_csv_skips_empty_relative_paths(tmp_path):
    csv_path = _write(tmp_path, "path,tar\n,archive.tar.gz\nx/1.mxl,archive.tar.gz\n")
    rows = list(read_pdmx_csv(csv_path))
    assert len(rows) == 1
    assert rows[0].relative_path == "x/1.mxl"


def test_read_pdmx_csv_missing_columns_raises(tmp_path):
    csv_path = _write(tmp_path, "foo,bar\n1,2\n")
    with pytest.raises(ValueError):
        list(read_pdmx_csv(csv_path))


def test_read_pdmx_csv_respects_explicit_column_names(tmp_path):
    csv_path = _write(tmp_path, "ruta,tar,url\nx/1.mxl,a.tar.gz,http://x\n")
    rows = list(read_pdmx_csv(csv_path, relative_path_col="ruta", archive_name_col="tar"))
    assert len(rows) == 1
    assert rows[0].relative_path == "x/1.mxl"
