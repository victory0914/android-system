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

import argparse
import logging
import os

import pytest
import yaml

import src.main_phase2 as main_phase2
from src.main_phase2 import (
    NetworkConfigError,
    _load_network_config,
    _parse_device_spec,
    _resolve_adb_path,
    _resolve_devices,
    build_arg_parser,
)
from src.orchestration.slot import SlotState


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


# --- --max-retries (2026-09-17): lets a manual debugging run stop after a
# single failure instead of repeating an identical error 3 times (the
# config-file default) before reporting it. -------------------------------


def test_max_retries_flag_defaults_to_none_meaning_use_config_value():
    args = build_arg_parser().parse_args(["--serial", "ABC123", "--model", "SHG10"])
    assert args.max_retries is None


def test_max_retries_flag_can_be_set_to_zero_for_a_single_attempt():
    args = build_arg_parser().parse_args(
        ["--serial", "ABC123", "--model", "SHG10", "--max-retries", "0"]
    )
    assert args.max_retries == 0


# --- --device (multi-device parallel mode, 2026-09-14) ---------------------


def test_parse_device_spec_splits_serial_and_model():
    assert _parse_device_spec("352063910272451:SHG10") == ("352063910272451", "SHG10")


@pytest.mark.parametrize("bad_spec", ["no-colon-here", ":SHG10", "352063910272451:", ""])
def test_parse_device_spec_rejects_malformed_input(bad_spec):
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_device_spec(bad_spec)


def test_build_arg_parser_accepts_repeated_device_flag():
    args = build_arg_parser().parse_args(
        ["--device", "SERIAL1:SHG10", "--device", "SERIAL2:SHG07"]
    )
    assert args.devices == [("SERIAL1", "SHG10"), ("SERIAL2", "SHG07")]
    assert args.serial is None
    assert args.model is None


def test_build_arg_parser_devices_defaults_to_none_in_single_device_mode():
    args = build_arg_parser().parse_args(["--serial", "ABC123", "--model", "SHG10"])
    assert args.devices is None


def test_resolve_devices_single_device_mode():
    args = build_arg_parser().parse_args(["--serial", "ABC123", "--model", "SHG10"])
    devices = _resolve_devices(args, build_arg_parser())
    assert devices == [("ABC123", "SHG10")]


def test_resolve_devices_multi_device_mode():
    args = build_arg_parser().parse_args(
        ["--device", "SERIAL1:SHG10", "--device", "SERIAL2:SHG07"]
    )
    devices = _resolve_devices(args, build_arg_parser())
    assert devices == [("SERIAL1", "SHG10"), ("SERIAL2", "SHG07")]


def test_resolve_devices_rejects_device_combined_with_serial():
    args = build_arg_parser().parse_args(
        ["--serial", "ABC123", "--model", "SHG10", "--device", "SERIAL2:SHG07"]
    )
    with pytest.raises(SystemExit):
        _resolve_devices(args, build_arg_parser())


def test_resolve_devices_rejects_neither_form_given():
    args = build_arg_parser().parse_args([])
    with pytest.raises(SystemExit):
        _resolve_devices(args, build_arg_parser())


def test_run_one_device_reports_unknown_model_without_touching_adb():
    """One device with a bad --device model_number must fail loud and
    return (not raise) — same philosophy as orchestration/scheduler.py's
    run_phase2_batch(): one bad device can't be allowed to crash a
    parallel batch for the others. Never even constructs an AdbClient for
    an unknown model, so this needs no real device."""
    serial, final_state, last_error = main_phase2._run_one_device(
        "ABC123",
        "NOT_A_REAL_MODEL",
        profiles={},
        network_config={},
        max_retry=3,
        adb_path="adb",
        skip_wizard=True,
    )
    assert serial == "ABC123"
    assert final_state == SlotState.ESCALATED
    assert "NOT_A_REAL_MODEL" in last_error


# --- Per-device network config overrides (2026-09-18) -----------------------
# Real finding: a physical unit's actual, installed SIM can have a
# different MCC/MNC than the rest of a batch — confirmed on SOG07 unit
# HQ632M1012, whose real SIM has MNC 10 while every other device in the
# same run uses config/network.yaml's shared MNC 11. Android silently
# rejects a new APN entry whose MCC/MNC doesn't match the active SIM's own,
# with no visible dialog and no error anywhere in this tool's own log —
# configure_apn() was working correctly the whole time; the shared config
# value was simply wrong for this one unit.

_BASE_NETWORK_CONFIG_WITH_OVERRIDE = {
    "wifi": {"ssid": "earth5_1", "password": "s3cret"},
    "apn": {"carrier": "Rakuten Mobile", "apn_name": "rakuten.jp", "mcc": "440", "mnc": "11"},
    "device_overrides": {
        "HQ632M1012": {"apn": {"mnc": "10"}},
    },
}


def test_resolve_device_network_config_applies_override_for_matching_serial():
    resolved = main_phase2._resolve_device_network_config(
        _BASE_NETWORK_CONFIG_WITH_OVERRIDE, "HQ632M1012"
    )
    assert resolved["apn"]["mnc"] == "10"
    # Every other key in `apn`, and the whole `wifi` section, unchanged —
    # a shallow per-section merge, not a wholesale replacement.
    assert resolved["apn"]["apn_name"] == "rakuten.jp"
    assert resolved["apn"]["mcc"] == "440"
    assert resolved["wifi"] == _BASE_NETWORK_CONFIG_WITH_OVERRIDE["wifi"]
    assert "device_overrides" not in resolved


def test_resolve_device_network_config_leaves_other_devices_unchanged():
    resolved = main_phase2._resolve_device_network_config(
        _BASE_NETWORK_CONFIG_WITH_OVERRIDE, "352063910272451"
    )
    assert resolved["apn"]["mnc"] == "11"
    assert "device_overrides" not in resolved


def test_resolve_device_network_config_never_mutates_the_base_config():
    original = {
        "wifi": {"ssid": "earth5_1", "password": "s3cret"},
        "apn": {"mnc": "11"},
        "device_overrides": {"HQ632M1012": {"apn": {"mnc": "10"}}},
    }
    snapshot = {k: dict(v) if isinstance(v, dict) else v for k, v in original.items()}
    main_phase2._resolve_device_network_config(original, "HQ632M1012")
    assert original == snapshot


def test_run_one_device_rejects_a_placeholder_value_introduced_by_an_override():
    """A per-device override that accidentally sets a placeholder value
    must be caught the same way the base config already is — real
    hardware showed silently proceeding with a placeholder leaves a
    garbage APN entry on the device."""
    from src.device.model_profile import ModelProfile

    network_config = {
        "wifi": {"ssid": "earth5_1", "password": "s3cret"},
        "apn": {"apn_name": "rakuten.jp", "mcc": "440", "mnc": "11"},
        "device_overrides": {
            "HQ632M1012": {"apn": {"mnc": "<mobile network code>"}},
        },
    }
    profile = ModelProfile(
        {
            "model": "Xperia 10 IV",
            "model_number": "SOG07",
            "manufacturer": "Sony",
            "android_version": 14,
            "wizard_steps": [],
            "wifi_settings": {},
            "apn_settings": {},
        }
    )
    serial, final_state, last_error = main_phase2._run_one_device(
        "HQ632M1012",
        "SOG07",
        profiles={"SOG07": profile},
        network_config=network_config,
        max_retry=3,
        adb_path="adb",
        skip_wizard=True,
    )
    assert serial == "HQ632M1012"
    assert final_state == SlotState.ESCALATED
    assert "apn.mnc" in last_error


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
