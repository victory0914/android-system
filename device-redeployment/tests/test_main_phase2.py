"""Tests for src/main_phase2.py — specifically _resolve_adb_path(), added
after a real client-PC run showed config/settings.yaml's
adb.platform_tools_path (a directory) was being passed straight through as
the adb executable itself, silently breaking every ADB call."""

import os

from src.main_phase2 import _resolve_adb_path


def test_resolve_adb_path_joins_directory_with_executable_name(tmp_path):
    exe_name = "adb.exe" if os.name == "nt" else "adb"
    (tmp_path / exe_name).write_text("", encoding="utf-8")

    result = _resolve_adb_path({"platform_tools_path": str(tmp_path)})

    assert result == str(tmp_path / exe_name)


def test_resolve_adb_path_falls_back_to_bare_adb_when_missing(tmp_path):
    # tmp_path exists but contains no adb executable.
    result = _resolve_adb_path({"platform_tools_path": str(tmp_path)})
    assert result == "adb"


def test_resolve_adb_path_falls_back_to_bare_adb_when_unconfigured():
    assert _resolve_adb_path({}) == "adb"
