"""Walks a device through its Android first-run setup-wizard (OOBE) screens.

Two schemas are supported, dispatched on `profile.has_screen_driven_wizard()`:

- **Legacy, sequence-driven** (`wizard_steps`): Stage A's original design —
  a fixed ordered list of {screen, resource_id, action, optional} steps,
  tapped by resource-id in order. Still used by the 3 models not yet given
  real wizard data (see PENDING_REAL_DEVICE_DATA.md).

- **Screen-driven, text-matching** (`wizard`): the Stage B design for SHG10.
  Real capture sessions established that OOBE wizard screens cannot be
  dumped remotely on these devices at all — ADB authorization is wiped by
  factory reset, and by the time ADB is available again the wizard is long
  gone (docs/record.md, "Wizard capture — RESOLVED AS NOT REMOTELY
  POSSIBLE"). Resource-ids are consequently unavailable; the client's
  photographed screen sequence gives reliable *visible text* instead. This
  mode identifies the current screen by its visible text, then acts —
  it does NOT assume a fixed order, since carrier/OTA screens appear
  conditionally. See docs/record.md, "IMPLEMENTATION SPEC — wizard via text
  matching", for the full per-screen spec this implements.

Never issues raw `client.shell("input tap ...")` calls directly — all screen
interaction goes through device/ui_automator.py.
"""

from __future__ import annotations

import logging
import time

from src.device.adb_client import AdbClientProtocol
from src.device.model_profile import ModelProfile
from src.device.ui_automator import (
    AmbiguousResourceIdError,
    all_visible_texts,
    dump_ui,
    find_by_text,
    scroll_down,
    tap_by_content_desc,
    tap_by_text,
    tap_resource_id,
    wait_for_text_to_disappear,
)

logger = logging.getLogger(__name__)

WIZARD_STEP_MAX_ATTEMPTS = 3
WIZARD_STEP_RETRY_DELAY_SECONDS = 2.0

# Screen-driven mode: how many screen-identify/act cycles to allow before
# giving up. Generous on purpose — spinner screens (wait_for_disappear) each
# consume only one cycle regardless of their own internal poll timeout.
SCREEN_DRIVEN_MAX_ITERATIONS = 20


def run_wizard(
    client: AdbClientProtocol,
    profile: ModelProfile,
    *,
    max_attempts: int = WIZARD_STEP_MAX_ATTEMPTS,
    retry_delay_seconds: float = WIZARD_STEP_RETRY_DELAY_SECONDS,
) -> bool:
    """Walk the device through its setup wizard. Dispatches to the
    screen-driven (text-matching) implementation if `profile` uses that
    schema, otherwise the legacy sequence-driven (resource-id) one."""
    if profile.has_screen_driven_wizard():
        return _run_screen_driven_wizard(client, profile)
    return _run_legacy_wizard(
        client, profile, max_attempts=max_attempts, retry_delay_seconds=retry_delay_seconds
    )


def _run_legacy_wizard(
    client: AdbClientProtocol,
    profile: ModelProfile,
    *,
    max_attempts: int,
    retry_delay_seconds: float,
) -> bool:
    """Walk through profile.wizard_steps() in order. For each step, call
    tap_resource_id(); if a step is marked optional and not found, continue;
    if a required step is not found after a short retry/backoff, return
    False."""
    for step in profile.wizard_steps():
        screen = step["screen"]
        resource_id = step["resource_id"]
        optional = step.get("optional", False)

        found = False
        for attempt in range(1, max_attempts + 1):
            found = tap_resource_id(client, resource_id)
            if found:
                logger.info("wizard step %r: tapped %r (attempt %d)", screen, resource_id, attempt)
                break
            if attempt < max_attempts:
                logger.debug(
                    "wizard step %r: %r not found (attempt %d/%d), retrying",
                    screen, resource_id, attempt, max_attempts,
                )
                time.sleep(retry_delay_seconds)

        if not found:
            if optional:
                logger.info("wizard step %r: optional and not found, skipping", screen)
                continue
            logger.error(
                "wizard step %r: required element %r not found after %d attempts",
                screen, resource_id, max_attempts,
            )
            return False

    return True


def _screen_is_present(ui_xml: str, identify_by_text: str) -> bool:
    try:
        return find_by_text(ui_xml, identify_by_text) is not None
    except AmbiguousResourceIdError:
        # Multiple nodes carrying this exact text still means "yes, we're on
        # this screen" for identification purposes — the ambiguity only
        # matters for *tapping*, which is handled separately by whichever
        # target_text the screen's action taps.
        return True


def _execute_screen_action(client: AdbClientProtocol, screen: dict) -> bool:
    action = screen["action"]

    if action == "tap_by_text":
        return tap_by_text(client, screen["target_text"])

    if action == "tap_by_content_desc":
        return tap_by_content_desc(client, screen["target_content_desc"])

    if action == "wait_for_disappear":
        timeout = screen.get("timeout_sec", 60)
        return wait_for_text_to_disappear(
            client, screen["identify_by_text"], timeout_seconds=timeout
        )

    if action == "scroll_then_tap_by_text":
        target = screen["target_text"]
        if tap_by_text(client, target):
            return True
        scroll_down(client)
        return tap_by_text(client, target)

    raise ValueError(f"wizard screen {screen.get('name')!r}: unknown action {action!r}")


def _run_screen_driven_wizard(
    client: AdbClientProtocol,
    profile: ModelProfile,
    *,
    max_iterations: int = SCREEN_DRIVEN_MAX_ITERATIONS,
) -> bool:
    """Screen-driven wizard walkthrough: each iteration, dump the UI,
    identify which configured screen (if any) is currently showing by its
    visible text, and act on it. Screens are handled at most once each but
    not required to appear (carrier/OTA screens are conditional). Fails
    loudly — logging the screen's full visible text — if a dump matches none
    of the configured screens and not all of them have been handled yet,
    rather than tapping blindly. Returns True once every configured screen
    has been handled.

    Note: there is no reliable, captured signal for "we've reached the home
    screen" (it varies with launcher/wallpaper and was never in scope for a
    real-device text/dump capture). Completion is instead defined as "the
    last screen in profile.wizard_screens() (its configured terminal screen,
    e.g. 「AQUOS Homeの通知アクセス」) has been handled" — NOT "every
    configured screen has been handled", since carrier/OTA screens are
    conditional and may legitimately never appear (docs/record.md). This is
    a deliberate simplification, not an oversight — see
    PENDING_REAL_DEVICE_DATA.md.
    """
    screens = profile.wizard_screens()
    terminal_name = screens[-1]["name"]
    done: set[str] = set()

    for _ in range(max_iterations):
        ui_xml = dump_ui(client)

        matched_screen = None
        for screen in screens:
            if screen["name"] in done:
                continue
            if _screen_is_present(ui_xml, screen["identify_by_text"]):
                matched_screen = screen
                break

        if matched_screen is None:
            if terminal_name in done:
                logger.info(
                    "wizard: terminal screen %r already handled, treating "
                    "flow as complete", terminal_name,
                )
                return True
            logger.error(
                "wizard: unrecognized screen — no configured screen's "
                "identify_by_text matched. Visible text on screen: %s",
                all_visible_texts(ui_xml),
            )
            return False

        name = matched_screen["name"]
        logger.info("wizard: on screen %r, executing action %r", name, matched_screen["action"])
        if not _execute_screen_action(client, matched_screen):
            logger.error("wizard: screen %r action %r failed", name, matched_screen["action"])
            return False

        done.add(name)

        if name == terminal_name:
            logger.info("wizard: reached and handled terminal screen %r", terminal_name)
            return True

    logger.error(
        "wizard: exceeded max_iterations (%d) without handling all configured "
        "screens (done=%s, expected=%s)",
        max_iterations, sorted(done), sorted(all_names),
    )
    return False
