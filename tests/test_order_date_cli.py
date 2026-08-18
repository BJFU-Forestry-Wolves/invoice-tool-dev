from pathlib import Path

import pytest

import order_date_cli


def test_privacy_outputs_must_be_outside_repository(tmp_path: Path):
    assert order_date_cli.ensure_outside_repository(tmp_path / "cache.sqlite3", "缓存") == (
        tmp_path / "cache.sqlite3"
    ).resolve()

    with pytest.raises(ValueError, match="Git 仓库外"):
        order_date_cli.ensure_outside_repository(order_date_cli.PROJECT_ROOT / "cache.sqlite3", "缓存")
