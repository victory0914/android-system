"""Small CLI entry point for manually running the Phase 2 flow (wizard,
Wi-Fi, APN) against one real, connected device.

Usage:
    python src/main_phase2.py --serial <adb_serial> --model <model_number>

This is what gets run manually against real hardware, once real config
values and real resource-ids are available (see PENDING_REAL_DEVICE_DATA.md
for what's still outstanding). It intentionally stays simple — it is not the
production dashboard (out of scope for Phase 2; see Section 22 of the spec).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Make `src.*` importable whether this file is run as `python src/main_phase2.py`
# or as `python -m src.main_phase2`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.device.adb_client import AdbClient
from src.device.model_profile import ModelProfile, ModelProfileError
from src.orchestration.scheduler import run_slot_with_retries
from src.orchestration.slot import Slot, SlotState

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS_DIR = REPO_ROOT / "config" / "models"
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"
DEFAULT_NETWORK_PATH = REPO_ROOT / "config" / "network.yaml"
DEFAULT_NETWORK_EXAMPLE_PATH = REPO_ROOT / "config" / "network.yaml.example"

logger = logging.getLogger("main_phase2")


def _load_settings(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


class NetworkConfigError(RuntimeError):
    """config/network.yaml is missing, or still contains a placeholder value
    copied verbatim from config/network.yaml.example, in one of the fields
    the automation actually reads."""


# Every placeholder string in config/network.yaml.example, verbatim — real
# evidence this matters, not just theoretical: a real SHG10 dump
# (tests/fixtures/apn_success_setting_SHG10.xml, 2026-09-11) showed a real
# leftover APN entry literally named "<APN value from client>" on the
# device — from some earlier run that silently fell back to this file
# (the old behavior here) instead of refusing to proceed.
_PLACEHOLDER_VALUES = {
    "<client-provided SSID>",
    "<client-provided password>",
    "<carrier name>",
    "<APN value from client>",
    "<mobile country code>",
    "<mobile network code>",
}

# Only the fields src/orchestration/slot.py actually reads
# (wifi_cfg.get("ssid"/"password"), apn_cfg.get("apn_name"/"mcc"/"mnc")) —
# NOT every key in the file. A first version of this check walked the
# whole config recursively and blocked a real run (2026-09-11) over
# apn.carrier still being "<carrier name>" — carrier is documentation only,
# never read by any code path, so refusing to proceed over it was a false
# positive: it protects nothing and just blocks otherwise-real, working
# config. Scoped to what's load-bearing instead.
_REQUIRED_CONFIG_PATHS = (
    ("wifi", "ssid"),
    ("wifi", "password"),
    ("apn", "apn_name"),
    ("apn", "mcc"),
    ("apn", "mnc"),
)


def _check_no_placeholder_values(config: dict) -> None:
    for path in _REQUIRED_CONFIG_PATHS:
        value = config
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value in _PLACEHOLDER_VALUES:
            full_key = ".".join(path)
            raise NetworkConfigError(
                f"config/network.yaml[{full_key!r}] is still the placeholder "
                f"value {value!r} copied from network.yaml.example — fill in "
                "a real value before running against real hardware."
            )


def _load_network_config(logger_: logging.Logger) -> dict:
    """Load config/network.yaml. Refuses to run at all if it's missing or
    still has a placeholder value — this always runs against real hardware
    (no dry-run mode), so silently falling back to obviously-fake example
    data isn't a safe default; it wastes a real device round-trip at best,
    and at worst (confirmed on real hardware, 2026-09-11 — see
    _PLACEHOLDER_VALUES's comment) leaves a garbage APN entry on the
    device."""
    if not DEFAULT_NETWORK_PATH.exists():
        raise NetworkConfigError(
            f"{DEFAULT_NETWORK_PATH} not found. Copy "
            f"{DEFAULT_NETWORK_EXAMPLE_PATH} to {DEFAULT_NETWORK_PATH} and "
            "fill in real values (it's gitignored — never committed) before "
            "running against real hardware."
        )

    with open(DEFAULT_NETWORK_PATH, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    _check_no_placeholder_values(config)
    return config


def _configure_logging(level_name: str, log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    level = getattr(logging, str(level_name).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Path(log_dir) / "main_phase2.log", encoding="utf-8"),
        ],
    )


def _resolve_adb_path(adb_cfg: dict) -> str:
    """Turn config/settings.yaml's `adb.platform_tools_path` — a *directory*
    (e.g. "C:\\platform-tools") — into the actual `adb` executable path to
    invoke. Passing the directory itself straight through used to be handed
    to subprocess as the command, which fails with OSError on every single
    call; AdbClient.is_connected() swallows that and returns False, which
    then misleadingly looks exactly like "device not connected" even when
    `adb devices` works fine in a normal shell. Falls back to bare "adb"
    (resolved via PATH) if platform_tools_path isn't configured or doesn't
    actually contain an adb executable, logging a clear warning either way
    rather than failing silently like the bug this replaces."""
    platform_tools_path = adb_cfg.get("platform_tools_path")
    if not platform_tools_path:
        return "adb"

    exe_name = "adb.exe" if os.name == "nt" else "adb"
    candidate = Path(platform_tools_path) / exe_name
    if candidate.is_file():
        return str(candidate)

    logger.warning(
        "adb.platform_tools_path (%r) does not contain %r; falling back to "
        "'adb' resolved via PATH. If that's not found either, every ADB "
        "call will fail with a misleading error.",
        platform_tools_path, exe_name,
    )
    return "adb"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 device-redeployment flow (wizard, Wi-Fi, "
        "APN) against one real, connected Android device."
    )
    parser.add_argument(
        "--serial", required=True, help="adb device serial (see `adb devices`)"
    )
    parser.add_argument(
        "--model",
        required=True,
        help="model_number of this device's profile (e.g. SOG08, SOG07, SHG07, SHG10)",
    )
    parser.add_argument(
        "--models-dir",
        default=str(DEFAULT_MODELS_DIR),
        help="directory containing config/models/*.yaml (default: %(default)s)",
    )
    parser.add_argument(
        "--settings",
        default=str(DEFAULT_SETTINGS_PATH),
        help="path to config/settings.yaml (default: %(default)s)",
    )
    parser.add_argument(
        "--skip-wizard",
        action="store_true",
        help="Skip the setup-wizard step and go straight to Wi-Fi/APN. For "
        "manual testing against a device that's already past OOBE (e.g. "
        "re-testing the same already-provisioned unit repeatedly without a "
        "fresh factory reset each time). Never use this for a real "
        "redeployment run — it removes the check that the device actually "
        "finished setup.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    settings = _load_settings(Path(args.settings))
    logging_cfg = settings.get("logging", {})
    _configure_logging(
        logging_cfg.get("level", "INFO"), logging_cfg.get("log_dir", "./logs")
    )

    adb_cfg = settings.get("adb", {})
    retry_cfg = settings.get("retry", {})
    max_retry = int(retry_cfg.get("max_retries", 3))

    logger.info("loading model profiles from %s", args.models_dir)
    try:
        profiles = ModelProfile.load_all(args.models_dir)
    except ModelProfileError as exc:
        logger.error("failed to load model profiles: %s", exc)
        return 1

    profile = profiles.get(args.model)
    if profile is None:
        logger.error(
            "unknown model %r; available: %s", args.model, sorted(profiles.keys())
        )
        return 1

    try:
        network_config = _load_network_config(logger)
    except NetworkConfigError as exc:
        logger.error("%s", exc)
        return 1

    adb_path = _resolve_adb_path(adb_cfg)
    client = AdbClient(args.serial, adb_path=adb_path)

    slot = Slot(args.serial, client, max_retry=max_retry)
    logger.info(
        "starting Phase 2 run: serial=%s model=%s (%s)%s",
        args.serial, args.model, profile.model,
        " [skip_wizard]" if args.skip_wizard else "",
    )

    final_state = run_slot_with_retries(
        slot, profile, network_config, skip_wizard=args.skip_wizard
    )

    if final_state == SlotState.LOGIN_INSTALL:
        logger.info("SUCCESS: device %s reached LOGIN_INSTALL", args.serial)
        return 0

    logger.error(
        "FAILED: device %s ended in state %s (last_error=%s)",
        args.serial, final_state.name, slot.last_error,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
