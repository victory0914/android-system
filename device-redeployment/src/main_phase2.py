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


def _load_network_config(logger_: logging.Logger) -> dict:
    if DEFAULT_NETWORK_PATH.exists():
        path = DEFAULT_NETWORK_PATH
    else:
        logger_.warning(
            "config/network.yaml not found; falling back to config/network.yaml.example "
            "(placeholder values only - this will not work against a real network)."
        )
        path = DEFAULT_NETWORK_EXAMPLE_PATH

    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


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

    network_config = _load_network_config(logger)

    adb_path = adb_cfg.get("platform_tools_path")
    client = AdbClient(args.serial, adb_path=str(adb_path) if adb_path else "adb")

    slot = Slot(args.serial, client, max_retry=max_retry)
    logger.info(
        "starting Phase 2 run: serial=%s model=%s (%s)",
        args.serial, args.model, profile.model,
    )

    final_state = run_slot_with_retries(slot, profile, network_config)

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
