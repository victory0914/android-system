"""Tests for src/main_phase2.py — _resolve_adb_path() (added after a real
client-PC run showed config/settings.yaml's adb.platform_tools_path, a
directory, was being passed straight through as the adb executable itself,
silently breaking every ADB call) and the --skip-wizard flag (added after
the same session showed the test unit was already past OOBE, with no way
to test Wi-Fi/APN against it without a full factory reset each time)."""

import os

from src.main_phase2 import _resolve_adb_path, build_arg_parser


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


def test_skip_wizard_flag_defaults_to_false():
    args = build_arg_parser().parse_args(["--serial", "ABC123", "--model", "SHG10"])
    assert args.skip_wizard is False


def test_skip_wizard_flag_can_be_set():
    args = build_arg_parser().parse_args(
        ["--serial", "ABC123", "--model", "SHG10", "--skip-wizard"]
    )
    assert args.skip_wizard is True
