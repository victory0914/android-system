"""Small CLI entry point for manually running the Phase 2 flow (wizard,
Wi-Fi, APN) against one or more real, connected devices.

Usage:
    python src/main_phase2.py --skip-wizard

With no --device/--serial/--model at all (the normal way to run this now,
2026-09-22 client decision), it auto-detects every currently-connected,
authorized device via `adb devices` + `getprop ro.product.model` and runs
all of them in parallel — no need to look up or type a serial by hand, and
a client swapping in a different physical unit doesn't require touching
this code or command at all. --serial/--model (one device) and --device
(repeatable, explicit SERIAL:MODEL pairs) both still work, for a manual
override or for a device auto-detection can't identify.

This is what gets run manually against real hardware, once real config
values and real resource-ids are available (see PENDING_REAL_DEVICE_DATA.md
for what's still outstanding). It intentionally stays simple — it is not the
production dashboard (out of scope for Phase 2; see Section 22 of the spec).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import logging
import os
import subprocess
import sys
from pathlib import Path

# Make `src.*` importable whether this file is run as `python src/main_phase2.py`
# or as `python -m src.main_phase2`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from src.device.adb_client import AdbClient, AdbCommandError
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


class AutoDetectError(RuntimeError):
    """Raised when device auto-detection fails outright — `adb` itself
    couldn't be invoked at all (bad adb_path, timeout). Distinct from a
    single connected device not matching a known model profile, which is
    logged and excluded per-device instead (see _auto_detect_devices())
    so it can't block the rest of a batch, matching this file's existing
    "one device's problem never takes down the others" philosophy."""


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


def _parse_device_spec(spec: str) -> tuple[str, str]:
    """Parse one `--device` value: "SERIAL:MODEL" (e.g.
    "352063910272451:SHG10"). Raises argparse.ArgumentTypeError (which
    argparse turns into a clean CLI error, not a traceback) if the format
    is wrong — a single serial with no `:` is a plausible typo (forgetting
    the model half), so this fails loud rather than guessing."""
    serial, sep, model = spec.partition(":")
    if not sep or not serial or not model:
        raise argparse.ArgumentTypeError(
            f"--device value {spec!r} must be SERIAL:MODEL "
            "(e.g. 352063910272451:SHG10)"
        )
    return serial, model


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2 device-redeployment flow (wizard, Wi-Fi, "
        "APN) against one or more real, connected Android devices. With none "
        "of --device/--serial/--model given, every connected, authorized "
        "device is auto-detected (adb devices + getprop ro.product.model) "
        "and run in parallel — this is the normal way to invoke a batch run."
    )
    parser.add_argument(
        "--serial",
        help="adb device serial (see `adb devices`) — single-device mode, "
        "overriding auto-detection for that one device. Mutually exclusive "
        "with --device; used together with --model.",
    )
    parser.add_argument(
        "--model",
        help="model_number of this device's profile (e.g. SOG08, SOG07, "
        "SHG07, SHG10) — single-device mode, used with --serial.",
    )
    parser.add_argument(
        "--device",
        action="append",
        dest="devices",
        metavar="SERIAL:MODEL",
        type=_parse_device_spec,
        help="Run multiple SPECIFIC devices IN PARALLEL, at the same time, "
        "against the same config/network.yaml — repeat for each device: "
        "--device 352063910272451:SHG10 --device <serial2>:SHG07. Each "
        "device gets its own retry loop; one device's failure never blocks "
        "or delays the others. Mutually exclusive with --serial/--model. "
        "Only needed to override auto-detection for specific devices — "
        "with no --device/--serial/--model at all, every connected device "
        "is auto-detected and run instead.",
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
        help="Skip the setup-wizard step and go straight to Wi-Fi/APN. "
        "This is the STANDARD way to invoke a real redeployment run "
        "(client decision, 2026-09-17): the wizard/OOBE screens cannot be "
        "automated via ADB at all (factory reset wipes ADB authorization "
        "until a human completes the wizard and re-enables USB "
        "debugging), so the client performs factory reset + the wizard "
        "manually for every device, and this automation takes over from "
        "there. Removes the check that the device actually finished "
        "setup — a device still mid-wizard when this runs will fail "
        "downstream instead.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Override config/settings.yaml's retry.max_retries (default: "
        "3) for this run only. 0 means a single attempt with no retries — "
        "useful while debugging a real-device issue, so an identical "
        "failure isn't repeated 3 times before you see the result. Never "
        "changes the config file itself.",
    )
    return parser


def _resolve_devices(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> list[tuple[str, str]] | None:
    """Reconcile --device (repeatable, multi-device) against --serial/--model
    (single-device convenience) into one list of (serial, model_number)
    pairs, or None if neither was given at all — the signal for
    main() to auto-detect every connected device instead (see
    _auto_detect_devices()). --device and --serial/--model are mutually
    exclusive, and --serial/--model must be given together (a lone one is
    a likely typo, not "please auto-detect the other half") — both call
    parser.error() (prints usage, exits 2), matching argparse's own
    convention for CLI-usage mistakes."""
    if args.devices and (args.serial or args.model):
        parser.error("--device cannot be combined with --serial/--model")
    if args.devices:
        return args.devices
    if args.serial or args.model:
        if not (args.serial and args.model):
            parser.error("--serial and --model must be given together")
        return [(args.serial, args.model)]
    return None


def _list_adb_devices(adb_path: str) -> list[tuple[str, str]]:
    """Run `adb devices` (global — no -s <serial>, there isn't one yet) and
    return every (serial, state) pair it reports, in the order given.
    Raises AutoDetectError if adb itself can't be invoked at all (bad
    adb_path, timeout) — mirrors AdbClient._run_raw()'s own OSError/
    TimeoutExpired handling for the same reason: silently swallowing this
    into "no devices found" would look identical to "nothing is plugged
    in" when the real problem is a misconfigured adb_path."""
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AutoDetectError(f"'{adb_path} devices' timed out after 10s") from exc
    except OSError as exc:
        raise AutoDetectError(
            f"could not execute adb at {adb_path!r}: {exc}. Is adb_path "
            "correct? (see config/settings.yaml's adb.platform_tools_path)"
        ) from exc

    pairs: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue  # e.g. the "List of devices attached" header, or a blank line
        pairs.append((parts[0], parts[1]))
    return pairs


def _detect_model_number(
    client: AdbClient, profiles: dict[str, ModelProfile]
) -> tuple[str | None, str]:
    """Identify which loaded model profile matches this connected device,
    via `adb shell getprop ro.product.model` — the same command the client
    has already been running by hand to identify units (see
    docs/record.md's SOG07/SOG08 sections: "client identified [it] via
    `adb devices` + `getprop ro.product.model`"). Returns
    (model_number_or_None, raw_getprop_value_for_logging).

    Matches case-insensitively against each profile's own `model_number`
    (e.g. "SOG08") or, if set, its optional `adb_identifiers` list (see
    ModelProfile.adb_identifiers()) — an escape hatch for a model whose
    real `ro.product.model` string turns out to differ from its carrier
    model number once that's actually confirmed on real hardware. Never
    guesses: returns None (no match) rather than picking a "closest"
    profile, and logs a clear error if the value matches more than one
    profile (ambiguous) rather than picking either one."""
    try:
        raw = client.shell("getprop ro.product.model").strip()
    except AdbCommandError as exc:
        return None, f"<getprop ro.product.model failed: {exc}>"

    raw_lower = raw.lower()
    matches = [
        model_number
        for model_number, profile in profiles.items()
        if raw_lower
        in {model_number.lower(), *(s.lower() for s in profile.adb_identifiers())}
    ]

    if len(matches) == 1:
        return matches[0], raw
    if len(matches) > 1:
        logger.error(
            "device %s: ambiguous model match — getprop ro.product.model "
            "= %r matches more than one profile: %s. Refusing to guess; "
            "disambiguate via each profile's adb_identifiers, or pass "
            "--serial/--model explicitly for this device.",
            client.serial, raw, matches,
        )
        return None, raw
    return None, raw


def _auto_detect_devices(
    adb_path: str, profiles: dict[str, ModelProfile]
) -> list[tuple[str, str]]:
    """Auto-detect every currently-connected, authorized device and match
    it to a known model profile — this runs when the CLI is invoked with
    no --device/--serial/--model at all, so a client can just plug in
    whatever devices they have and run one simple command, instead of
    looking up and typing each serial/model by hand every time a
    different physical unit gets connected.

    Never guesses: a device that isn't in the 'device' (ready/authorized)
    state, or doesn't cleanly match exactly one known profile, is logged
    as a clear error/warning and excluded — never silently skipped
    without explanation, and never run against a "closest" or default
    profile."""
    pairs = _list_adb_devices(adb_path)

    serials: list[str] = []
    for serial, state in pairs:
        if state == "device":
            serials.append(serial)
        else:
            logger.warning(
                "device %s: adb reports state %r (not 'device'/ready) — "
                "skipping. A common cause is an unaccepted USB debugging "
                "authorization prompt on the device itself.",
                serial, state,
            )

    devices: list[tuple[str, str]] = []
    for serial in serials:
        client = AdbClient(serial, adb_path=adb_path)
        model_number, raw = _detect_model_number(client, profiles)
        if model_number is None:
            logger.error(
                "device %s: could not match to a known model profile "
                "(getprop ro.product.model = %r). Known model_numbers: "
                "%s. Run it explicitly with --serial %s --model <MODEL> "
                "once you know which profile it is — and if %r is that "
                "model's real identity string, add it to that model's "
                "config/models/*.yaml under adb_identifiers so "
                "auto-detection recognizes it next time.",
                serial, raw, sorted(profiles.keys()), serial, raw,
            )
            continue
        logger.info(
            "device %s: auto-detected as %s (getprop ro.product.model = %r)",
            serial, model_number, raw,
        )
        devices.append((serial, model_number))
    return devices


def _resolve_device_network_config(base_config: dict, serial: str) -> dict:
    """Merge `base_config`'s shared `wifi`/`apn` blocks with any
    per-device override for `serial` under `device_overrides`, and return
    the resolved config for that one device — `base_config` itself is
    never mutated, and every other device keeps seeing the unmodified
    shared config.

    Real finding (2026-09-18): a physical unit's actually-installed SIM
    can have a different MCC/MNC than the rest of a batch — confirmed on
    SOG07 unit HQ632M1012, whose real SIM has MNC 10 while every other
    device in the same run uses the shared config's MNC 11. Android
    silently rejects a new APN entry whose MCC/MNC doesn't match the
    active SIM's own, with no visible dialog and no error anywhere in
    this tool's own log — `configure_apn()` was working correctly the
    whole time; the config value was simply wrong for this one unit.
    `config/network.yaml`'s single shared `apn` block can't represent
    that, hence this override mechanism.

    A shallow merge per top-level section (`wifi`/`apn`), not a deep
    recursive merge — an override only needs to replace the specific
    keys it sets (e.g. just `mnc`), leaving every other key in that
    section (and any other section) exactly as the shared config has it.
    That's all the schema currently needs; a deeper merge would just be
    unused complexity.
    """
    resolved = {k: v for k, v in base_config.items() if k != "device_overrides"}
    overrides = base_config.get("device_overrides", {}).get(serial)
    if not overrides:
        return resolved
    for section, section_overrides in overrides.items():
        if isinstance(section_overrides, dict) and isinstance(resolved.get(section), dict):
            resolved[section] = {**resolved[section], **section_overrides}
        else:
            resolved[section] = section_overrides
    return resolved


def _run_one_device(
    serial: str,
    model_number: str,
    *,
    profiles: dict[str, ModelProfile],
    network_config: dict,
    max_retry: int,
    adb_path: str,
    skip_wizard: bool,
) -> tuple[str, SlotState, str | None]:
    """Run Phase 2 against one device and return (serial, final_state,
    last_error) — never raises, so one device's problem can't take down a
    parallel batch of others (same philosophy as
    orchestration/scheduler.py's run_phase2_batch())."""
    profile = profiles.get(model_number)
    if profile is None:
        error = f"unknown model {model_number!r}; available: {sorted(profiles.keys())}"
        logger.error("device %s: %s", serial, error)
        return serial, SlotState.ESCALATED, error

    device_network_config = _resolve_device_network_config(network_config, serial)
    if serial in network_config.get("device_overrides", {}):
        logger.info(
            "device %s: applying per-device network config override "
            "(config/network.yaml's device_overrides)",
            serial,
        )
        try:
            _check_no_placeholder_values(device_network_config)
        except NetworkConfigError as exc:
            logger.error("device %s: %s", serial, exc)
            return serial, SlotState.ESCALATED, str(exc)

    client = AdbClient(serial, adb_path=adb_path)
    slot = Slot(serial, client, max_retry=max_retry)
    logger.info(
        "starting Phase 2 run: serial=%s model=%s (%s)%s",
        serial, model_number, profile.model,
        " [skip_wizard]" if skip_wizard else "",
    )

    final_state = run_slot_with_retries(
        slot, profile, device_network_config, skip_wizard=skip_wizard
    )
    return serial, final_state, slot.last_error


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    devices = _resolve_devices(args, parser)

    settings = _load_settings(Path(args.settings))
    logging_cfg = settings.get("logging", {})
    _configure_logging(
        logging_cfg.get("level", "INFO"), logging_cfg.get("log_dir", "./logs")
    )

    adb_cfg = settings.get("adb", {})
    retry_cfg = settings.get("retry", {})
    max_retry = int(retry_cfg.get("max_retries", 3))
    if args.max_retries is not None:
        max_retry = args.max_retries
        logger.info("--max-retries override: using %d instead of config's default", max_retry)

    logger.info("loading model profiles from %s", args.models_dir)
    try:
        profiles = ModelProfile.load_all(args.models_dir)
    except ModelProfileError as exc:
        logger.error("failed to load model profiles: %s", exc)
        return 1

    try:
        network_config = _load_network_config(logger)
    except NetworkConfigError as exc:
        logger.error("%s", exc)
        return 1

    adb_path = _resolve_adb_path(adb_cfg)

    if devices is None:
        logger.info(
            "no --device/--serial given — auto-detecting connected "
            "devices via '%s devices' + getprop ro.product.model",
            adb_path,
        )
        try:
            devices = _auto_detect_devices(adb_path, profiles)
        except AutoDetectError as exc:
            logger.error("%s", exc)
            return 1
        if not devices:
            logger.error(
                "auto-detection found no connected device that matches a "
                "known model profile — nothing to run. Connect a device "
                "(and accept its USB debugging prompt), or pass "
                "--serial/--model explicitly."
            )
            return 1
        logger.info(
            "auto-detected %d device(s): %s",
            len(devices), ", ".join(f"{serial}:{model}" for serial, model in devices),
        )

    # Single device: run inline, exactly as before (no thread pool overhead
    # or interleaved logging from a second thread for the common case).
    # Multiple devices: dispatch all of them AT THE SAME TIME via a thread
    # pool — each has its own Slot/AdbClient/retry loop, sharing only the
    # loaded model profiles and network_config (same real network target
    # for every device in the batch, matching how config/network.yaml is
    # structured — one Wi-Fi/APN pair, not one per device).
    if len(devices) == 1:
        serial, model_number = devices[0]
        results = [
            _run_one_device(
                serial, model_number,
                profiles=profiles, network_config=network_config,
                max_retry=max_retry, adb_path=adb_path, skip_wizard=args.skip_wizard,
            )
        ]
    else:
        logger.info(
            "running %d devices in parallel: %s",
            len(devices), ", ".join(f"{serial}:{model}" for serial, model in devices),
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as executor:
            futures = [
                executor.submit(
                    _run_one_device, serial, model_number,
                    profiles=profiles, network_config=network_config,
                    max_retry=max_retry, adb_path=adb_path, skip_wizard=args.skip_wizard,
                )
                for serial, model_number in devices
            ]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]

    exit_code = 0
    for serial, final_state, last_error in results:
        if final_state == SlotState.LOGIN_INSTALL:
            logger.info("SUCCESS: device %s reached LOGIN_INSTALL", serial)
        else:
            logger.error(
                "FAILED: device %s ended in state %s (last_error=%s)",
                serial, final_state.name, last_error,
            )
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
