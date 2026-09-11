"""Tests for src/main_phase2.py — _resolve_adb_path() (added after a real
client-PC run showed config/settings.yaml's adb.platform_tools_path, a
directory, was being passed straight through as the adb executable itself,
silently breaking every ADB call), the --skip-wizard flag (added after
the same session showed the test unit was already past OOBE, with no way
to test Wi-Fi/APN against it without a full factory reset each time), and
_load_network_config()'s placeholder-value guard (added after a real SHG10
dump, 2026-09-11, showed a leftover APN entry literally named "<APN value
from client>" on the device — evidence that silently falling back to
config/network.yaml.example's placeholder data, the old behavior, is
unsafe: this always runs against real hardware, there is no dry-run mode)."""

import logging
import os

import pytest
import yaml

import src.main_phase2 as main_phase2
from src.main_phase2 import (
    NetworkConfigError,
    _load_network_config,
    _resolve_adb_path,
    build_arg_parser,
)


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


# --- _load_network_config placeholder-value guard (2026-09-11) -------------

_REAL_NETWORK_CONFIG = {
    "wifi": {"ssid": "earth5_1", "password": "s3cret"},
    "apn": {
        "carrier": "Rakuten Mobile",
        "apn_name": "rakuten.jp",
        "mcc": "440",
        "mnc": "11",
    },
}


def test_load_network_config_raises_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(main_phase2, "DEFAULT_NETWORK_PATH", tmp_path / "network.yaml")
    with pytest.raises(NetworkConfigError, match="not found"):
        _load_network_config(logging.getLogger("test"))


def test_load_network_config_raises_on_placeholder_apn_name(tmp_path, monkeypatch):
    """The exact real-world case: config/network.yaml exists but a field
    inside it was never actually filled in, still reading the literal
    example text."""
    config = {
        "wifi": {"ssid": "earth5_1", "password": "s3cret"},
        "apn": {"apn_name": "<APN value from client>", "mcc": "440", "mnc": "11"},
    }
    path = tmp_path / "network.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(main_phase2, "DEFAULT_NETWORK_PATH", path)

    with pytest.raises(NetworkConfigError, match="apn_name"):
        _load_network_config(logging.getLogger("test"))


def test_load_network_config_raises_on_placeholder_wifi_ssid(tmp_path, monkeypatch):
    config = {
        "wifi": {"ssid": "<client-provided SSID>", "password": "s3cret"},
        "apn": {"apn_name": "rakuten.jp", "mcc": "440", "mnc": "11"},
    }
    path = tmp_path / "network.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(main_phase2, "DEFAULT_NETWORK_PATH", path)

    with pytest.raises(NetworkConfigError, match="ssid"):
        _load_network_config(logging.getLogger("test"))


def test_load_network_config_succeeds_with_real_values(tmp_path, monkeypatch):
    path = tmp_path / "network.yaml"
    path.write_text(yaml.safe_dump(_REAL_NETWORK_CONFIG), encoding="utf-8")
    monkeypatch.setattr(main_phase2, "DEFAULT_NETWORK_PATH", path)

    result = _load_network_config(logging.getLogger("test"))

    assert result == _REAL_NETWORK_CONFIG


def test_load_network_config_ignores_placeholder_in_unread_field(tmp_path, monkeypatch):
    """Regression test for the exact real failure this guard caused
    (2026-09-11): a real client run with a genuinely-filled-in config was
    blocked because apn.carrier — never read by any code path
    (src/orchestration/slot.py only reads apn_name/mcc/mnc) — still had its
    placeholder text. The guard must only check fields that are actually
    load-bearing (_REQUIRED_CONFIG_PATHS), not every key in the file."""
    config = {
        "wifi": {"ssid": "earth5_1", "password": "s3cret"},
        "apn": {
            "carrier": "<carrier name>",  # left as placeholder — must be fine
            "apn_name": "rakuten.jp",
            "mcc": "440",
            "mnc": "11",
        },
    }
    path = tmp_path / "network.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(main_phase2, "DEFAULT_NETWORK_PATH", path)

    result = _load_network_config(logging.getLogger("test"))

    assert result == config
