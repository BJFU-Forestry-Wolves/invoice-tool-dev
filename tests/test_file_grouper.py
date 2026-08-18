import hashlib
from pathlib import Path

from order_date.file_grouper import extract_bx_id, scan_order_files


def test_extract_bx_id_is_exact():
    assert extract_bx_id("BX123(2).JPEG") == "BX123"
    assert extract_bx_id("BX123-extra.jpg") is None
    assert extract_bx_id("not-an-id.png") is None


def test_scan_order_files_validates_extensions_and_hashes(tmp_path: Path):
    (tmp_path / "BX123.jpg").write_bytes(b"image")
    (tmp_path / "BX124.exe").write_bytes(b"bad")
    (tmp_path / "renamed.png").write_bytes(b"bad-name")

    result = scan_order_files(tmp_path)

    assert len(result.files) == 1
    assert result.files[0].file_hash == hashlib.sha256(b"image").hexdigest()
    assert {issue.code for issue in result.issues} == {"UNSUPPORTED_EXTENSION", "INVALID_BX_FILENAME"}
