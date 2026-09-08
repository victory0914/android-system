"""Connects a device to a Wi-Fi network: tries the `cmd wifi` shell command
first, falls back to UI Automator against the model's wifi_settings.

Never issues raw ADB shell taps directly for screen interaction — all screen
interaction goes through device/ui_automator.py.
"""

from __future__ import annotations

import logging
import re
import time

from src.device.adb_client import AdbClientProtocol, AdbCommandError
from src.device.model_profile import ModelProfile
from src.device.ui_automator import (
    dump_ui,
    inject_text,
    navigate_menu_path,
    node_is_checked,
    tap_resource_id,
)

logger = logging.getLogger(__name__)

CONNECT_POLL_TIMEOUT_SECONDS = 30
CONNECT_POLL_INTERVAL_SECONDS = 2.0


def _is_wifi_connected(client: AdbClientProtocol, ssid: str) -> bool:
    """Poll `adb shell dumpsys wifi` and confirm the device actually reports
    an active connection to `ssid`, rather than assuming a prior command's
    exit code was the whole truth."""
    try:
        output = client.shell("dumpsys wifi")
    except AdbCommandError:
        return False

    quoted_ssid = f'"{ssid}"'
    if quoted_ssid not in output:
        return False

    # Look for a connected/completed state marker near the SSID mention.
    # Real dumpsys wifi output includes lines like:
    #   mNetworkInfo: type: WIFI, state: CONNECTED/CONNECTED, reason: ...
    #   SSID: "MySSID", ... state: COMPLETED
    return bool(re.search(r"state:\s*(CONNECTED|COMPLETED)", output, re.IGNORECASE))


def _wait_for_connection(
    client: AdbClientProtocol,
    ssid: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _is_wifi_connected(client, ssid):
            return True
        time.sleep(poll_interval_seconds)
    return _is_wifi_connected(client, ssid)


def _try_shell_connect(client: AdbClientProtocol, ssid: str, password: str) -> bool:
    """Try `adb shell cmd wifi connect-network <ssid> wpa2 <password>`.
    Return True if the command ran without error (does NOT by itself mean
    connected — caller still polls to confirm)."""
    escaped_ssid = ssid.replace('"', '\\"')
    escaped_password = password.replace('"', '\\"')
    try:
        client.shell(f'cmd wifi connect-network "{escaped_ssid}" wpa2 "{escaped_password}"')
        return True
    except AdbCommandError as exc:
        logger.info("shell wifi connect-network unavailable/failed: %s", exc)
        return False


def _ensure_wifi_toggle_on(client: AdbClientProtocol, toggle_resource_id: str) -> None:
    """Check the toggle's actual on/off state before touching it — a real
    SHG10 capture (tests/fixtures/wifi_list_SHG10.xml) showed the toggle as a
    plain Switch with a `checked` attribute, and Wi-Fi was already ON in that
    capture. Blindly tapping a toggle without checking its state risks
    turning Wi-Fi *off* instead of on — see docs/record.md Task 1 note:
    'the Wi-Fi toggle must be ON before the SSID list renders at all'."""
    ui_xml = dump_ui(client)
    checked = node_is_checked(ui_xml, toggle_resource_id)
    if checked is None:
        logger.warning(
            "wifi toggle %r not found in current dump; cannot confirm on/off "
            "state, skipping toggle tap to avoid guessing",
            toggle_resource_id,
        )
        return
    if checked:
        logger.debug("wifi toggle %r already on; not tapping it", toggle_resource_id)
        return
    tap_resource_id(client, toggle_resource_id)


def _try_ui_connect(
    client: AdbClientProtocol, profile: ModelProfile, ssid: str, password: str
) -> None:
    """Best-effort UI Automator fallback: navigate to the Wi-Fi settings
    screen (if a menu_path is configured), ensure Wi-Fi is on (without
    blindly tapping the toggle — see _ensure_wifi_toggle_on), select the
    network row matching `ssid` by text, enter the password, and tap
    connect."""
    wifi = profile.wifi_settings()

    menu_path = wifi.get("menu_path")
    if menu_path and not navigate_menu_path(client, menu_path):
        logger.warning("wifi UI fallback: could not navigate to Wi-Fi settings screen")
        return

    _ensure_wifi_toggle_on(client, wifi["toggle_resource_id"])

    # The SSID list only renders once Wi-Fi is confirmed on (see above) — a
    # fresh dump is needed post-toggle, which tap_resource_id takes care of
    # internally on its next call.
    selected = tap_resource_id(client, wifi["network_list_resource_id"], text=ssid)
    if not selected:
        logger.warning("wifi UI fallback: network %r not found in scanned list", ssid)
        return

    password_field = wifi.get("password_field_resource_id")
    if password_field:
        tap_resource_id(client, password_field)
    inject_text(client, password)

    connect_button = wifi.get("connect_button_resource_id")
    if connect_button:
        tap_resource_id(client, connect_button)


def connect_wifi(
    client: AdbClientProtocol,
    profile: ModelProfile,
    ssid: str,
    password: str,
    *,
    poll_timeout_seconds: float = CONNECT_POLL_TIMEOUT_SECONDS,
    poll_interval_seconds: float = CONNECT_POLL_INTERVAL_SECONDS,
) -> bool:
    """Try `adb shell cmd wifi connect-network <ssid> wpa2 <password>` first
    (works on Android 10+ in many cases). If that fails or is unavailable,
    fall back to UI Automator against profile.wifi_settings() resource-ids.
    Return True once connected — confirmed by polling `dumpsys wifi`, not
    just by assuming the command succeeded."""
    try:
        client.shell("svc wifi enable")
    except AdbCommandError as exc:
        logger.warning("could not explicitly enable wifi radio: %s", exc)

    shell_attempted = _try_shell_connect(client, ssid, password)
    if shell_attempted:
        if _wait_for_connection(client, ssid, poll_timeout_seconds, poll_interval_seconds):
            logger.info("connected to %r via shell command", ssid)
            return True
        logger.info("shell connect-network ran but connection not confirmed; falling back to UI")

    _try_ui_connect(client, profile, ssid, password)

    if _wait_for_connection(client, ssid, poll_timeout_seconds, poll_interval_seconds):
        logger.info("connected to %r via UI fallback", ssid)
        return True

    logger.error("failed to connect to %r via shell command or UI fallback", ssid)
    return False
