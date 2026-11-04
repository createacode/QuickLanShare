from __future__ import annotations

from pathlib import Path

from quicklanshare.utils.downloads import (
    default_download_dir,
    known_download_dir,
    resolve_download_dir,
    unique_download_path,
)


def test_default_download_dir_exists(qtbot) -> None:
    path = default_download_dir()
    assert path.is_absolute()
    assert path.is_dir()


def test_known_download_dir_is_absolute(qtbot) -> None:
    path = known_download_dir()
    assert path.is_absolute()


def test_custom_download_dir_on_other_drive(qtbot, tmp_path: Path) -> None:
    custom = tmp_path / "D_Downloads"
    custom.mkdir()
    assert resolve_download_dir(str(custom)) == custom


def test_missing_custom_dir_falls_back(qtbot, tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    assert resolve_download_dir(str(missing)) == default_download_dir()


def test_unique_download_path_avoids_overwrite(qtbot, tmp_path: Path) -> None:
    first = tmp_path / "报告 2026.txt"
    first.write_text("old", encoding="utf-8")
    target = unique_download_path(tmp_path, "报告 2026.txt")
    assert target == tmp_path / "报告 2026 (1).txt"
