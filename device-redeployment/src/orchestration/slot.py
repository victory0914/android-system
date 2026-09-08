"""Tracks one physical USB slot's device and its Phase 2 processing state.

Phase 3 will extend SlotState/Slot with the LOGIN_INSTALL -> ... transition's
actual logic (Google login, app install, Managed Google Play enrollment).
For Phase 2, reaching LOGIN_INSTALL is the success condition and this module
stops there.
"""

from __future__ import annotations

import logging
from enum import Enum, auto

from src.device.adb_client import AdbClientProtocol, AdbCommandError
from src.device.model_profile import ModelProfile
from src.phase2.apn_setup import configure_apn
from src.phase2.wifi_setup import connect_wifi
from src.phase2.wizard_walkthrough import run_wizard

logger = logging.getLogger(__name__)


def _prep_device(client: AdbClientProtocol, slot_id: str) -> None:
    """One-time device prep before the Phase 2 flow starts.

    `svc power stayon usb` keeps the screen from timing out while the
    device is cabled — without it, a device sitting idle mid-workflow (e.g.
    during a long wizard spinner) can fall asleep and interrupt UI
    automation, which matters a lot at 200 devices/hour (docs/record.md,
    "Operational note for Phase 2/3"). Best-effort: log and continue rather
    than fail the whole run if this one prep command doesn't succeed — the
    flow may still complete fine within the default timeout.
    """
    try:
        client.shell("svc power stayon usb")
    except AdbCommandError as exc:
        logger.warning(
            "slot %s: could not set 'stayon usb' (screen may time out mid-run): %s",
            slot_id, exc,
        )


class SlotState(Enum):
    IDLE = auto()
    INIT_APN = auto()
    LOGIN_INSTALL = auto()          # Phase 3 will implement this transition's
                                     # target logic — for Phase 2, treat reaching
                                     # this state as the success condition and stop.
    WAITING_FOR_HUMAN = auto()
    FAILED = auto()
    ESCALATED = auto()


class Slot:
    """Tracks one physical USB slot's device and its processing state."""

    def __init__(self, slot_id: str, client: AdbClientProtocol,
                 max_retry: int = 3):
        self.slot_id = slot_id
        self.client = client
        self.state = SlotState.IDLE
        self.retry_count = 0
        self.max_retry = max_retry
        self.last_error: str | None = None

    def run_init_apn(
        self, profile: ModelProfile, network_config: dict, *, skip_wizard: bool = False
    ) -> bool:
        """Execute the Phase 2 flow (wizard, Wi-Fi, APN) for this slot's
        device via the phase2/ module functions. Update self.state as it
        progresses. Return True on success, False on failure (and set
        self.last_error with a human-readable reason).

        `skip_wizard`: bypass the setup-wizard step entirely and go straight
        to Wi-Fi/APN. For manual testing against a device that's already
        past OOBE (e.g. re-testing the same unit repeatedly without a fresh
        factory reset each time) — never intended for a production batch
        run, since it removes the "did the device actually finish setup"
        check. `main_phase2.py --skip-wizard` is the only place this is
        wired up to an explicit, deliberate opt-in; `run_phase2_batch()`
        has no equivalent knob on purpose.
        """
        self.state = SlotState.INIT_APN
        self.last_error = None

        wifi_cfg = network_config.get("wifi", {})
        apn_cfg = network_config.get("apn", {})

        try:
            if not self.client.is_connected():
                raise RuntimeError(f"device on slot {self.slot_id!r} is not connected")

            _prep_device(self.client, self.slot_id)

            if skip_wizard:
                logger.warning(
                    "slot %s: skip_wizard=True - assuming the device is "
                    "already past setup (e.g. re-testing an already-"
                    "provisioned unit). This bypasses a real safety check; "
                    "never use this for a production batch run.",
                    self.slot_id,
                )
            else:
                logger.info("slot %s: running setup wizard", self.slot_id)
                if not run_wizard(self.client, profile):
                    raise RuntimeError("setup wizard did not complete (required step missing)")

            logger.info("slot %s: connecting wifi", self.slot_id)
            if not connect_wifi(
                self.client, profile, wifi_cfg.get("ssid", ""), wifi_cfg.get("password", "")
            ):
                raise RuntimeError("wifi connection failed")

            logger.info("slot %s: configuring apn", self.slot_id)
            if not configure_apn(
                self.client,
                profile,
                apn_cfg.get("apn_name", ""),
                apn_cfg.get("mcc", ""),
                apn_cfg.get("mnc", ""),
            ):
                raise RuntimeError("apn configuration failed")

        except Exception as exc:
            self.state = SlotState.FAILED
            self.last_error = str(exc)
            logger.error("slot %s: run_init_apn failed: %s", self.slot_id, self.last_error)
            return False

        self.state = SlotState.LOGIN_INSTALL
        logger.info("slot %s: reached LOGIN_INSTALL (Phase 2 success condition)", self.slot_id)
        return True
