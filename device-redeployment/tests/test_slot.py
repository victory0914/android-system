"""Tests for src/orchestration/slot.py: Slot.run_init_apn() end to end
against FakeAdbClient, plus the retry/escalation behavior in
run_slot_with_retries() (orchestration/scheduler.py) since Slot itself only
performs a single attempt per call — see that module's docstring."""

import pytest

from src.device.adb_client import AdbCommandError
from src.device.model_profile import ModelProfile
from src.orchestration.scheduler import run_slot_with_retries
from src.orchestration.slot import Slot, SlotState
from tests.fakes import FakeAdbClient

PROFILE_DATA = {
    "model": "Test Model",
    "model_number": "TST01",
    "manufacturer": "Test",
    "android_version": 13,
    "wizard_steps": [
        {"screen": "language_select", "resource_id": "wiz:next", "action": "tap"},
        {"screen": "skip_sim_check", "resource_id": "wiz:skip", "action": "tap", "optional": True},
    ],
    "wifi_settings": {
        "toggle_resource_id": "wifi:toggle",
        "network_list_resource_id": "wifi:list",
    },
    "apn_settings": {
        "menu_path": ["Settings", "Network"],
        "name_field_resource_id": "apn:name",
        "apn_field_resource_id": "apn:apn",
        "save_button_resource_id": "apn:save",
    },
}

NETWORK_CONFIG = {
    "wifi": {"ssid": "TestSSID", "password": "hunter2"},
    "apn": {"apn_name": "internet", "mcc": "310", "mnc": "260"},
}

# A single dump containing every element every step in PROFILE_DATA could
# possibly need — used once everything should be found first try.
FULL_SCREEN_XML = """<hierarchy>
  <node resource-id="wiz:next" text="Next" bounds="[0,0][100,100]" />
  <node resource-id="wiz:skip" text="Skip" bounds="[0,100][100,200]" />
  <node text="Settings" bounds="[0,200][100,300]" />
  <node text="Network" bounds="[0,300][100,400]" />
  <node resource-id="apn:name" bounds="[0,400][100,500]" />
  <node resource-id="apn:apn" bounds="[0,500][100,600]" />
  <node resource-id="apn:save" bounds="[0,600][100,700]" />
</hierarchy>"""

# A dump missing "wiz:next" (the first, required wizard step) — used to
# exercise wizard_walkthrough's built-in per-step retry.
SCREEN_WITHOUT_WIZ_NEXT_XML = """<hierarchy>
  <node resource-id="wiz:skip" text="Skip" bounds="[0,100][100,200]" />
</hierarchy>"""

DUMPSYS_WIFI_CONNECTED = 'SSID: "TestSSID", state: COMPLETED'


def _profile() -> ModelProfile:
    return ModelProfile(dict(PROFILE_DATA))


def test_run_init_apn_full_success_path():
    client = FakeAdbClient(
        ui_dumps=[FULL_SCREEN_XML],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
        connected=True,
    )
    slot = Slot("slot-1", client, max_retry=3)

    result = slot.run_init_apn(_profile(), NETWORK_CONFIG)

    assert result is True
    assert slot.state == SlotState.LOGIN_INSTALL
    assert slot.last_error is None
    assert "svc power stayon usb" in client.shell_calls


def test_run_init_apn_device_prep_failure_does_not_block_success():
    """`svc power stayon usb` is best-effort device prep (docs/record.md) —
    if it fails, the rest of the flow should still proceed normally."""
    client = FakeAdbClient(
        ui_dumps=[FULL_SCREEN_XML],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
        shell_failures={"svc power stayon usb"},
        connected=True,
    )
    slot = Slot("slot-1b", client, max_retry=3)

    result = slot.run_init_apn(_profile(), NETWORK_CONFIG)

    assert result is True
    assert slot.state == SlotState.LOGIN_INSTALL


def test_run_init_apn_skip_wizard_bypasses_wizard_entirely():
    """--skip-wizard (main_phase2.py) is for testing against a device that's
    already past OOBE — e.g. a home screen with none of the wizard's
    resource-ids present at all. If skip_wizard didn't actually bypass
    run_wizard(), this would fail (required step "wiz:next" not found);
    since it succeeds, the wizard step was genuinely never invoked."""
    home_screen_no_wizard_elements_xml = """<hierarchy>
  <node text="Settings" bounds="[0,200][100,300]" />
  <node text="Network" bounds="[0,300][100,400]" />
  <node resource-id="apn:name" bounds="[0,400][100,500]" />
  <node resource-id="apn:apn" bounds="[0,500][100,600]" />
  <node resource-id="apn:save" bounds="[0,600][100,700]" />
</hierarchy>"""
    client = FakeAdbClient(
        ui_dumps=[home_screen_no_wizard_elements_xml],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
        connected=True,
    )
    slot = Slot("slot-skip", client, max_retry=3)

    result = slot.run_init_apn(_profile(), NETWORK_CONFIG, skip_wizard=True)

    assert result is True
    assert slot.state == SlotState.LOGIN_INSTALL


def test_run_init_apn_without_skip_wizard_fails_on_same_screen(monkeypatch):
    """Sanity check for the test above: the same home-screen dump, without
    skip_wizard, must fail at the wizard step (proving the previous test's
    success really did come from bypassing it, not from the wizard
    tolerating a missing element some other way)."""
    monkeypatch.setattr("src.phase2.wizard_walkthrough.time.sleep", lambda _s: None)
    home_screen_no_wizard_elements_xml = """<hierarchy>
  <node text="Settings" bounds="[0,200][100,300]" />
</hierarchy>"""
    client = FakeAdbClient(ui_dumps=[home_screen_no_wizard_elements_xml], connected=True)
    slot = Slot("slot-no-skip", client, max_retry=3)

    result = slot.run_init_apn(_profile(), NETWORK_CONFIG, skip_wizard=False)

    assert result is False
    assert slot.state == SlotState.FAILED


def test_run_init_apn_step_fails_then_succeeds_on_retry(monkeypatch):
    # Skip the real backoff sleep so the test stays fast.
    monkeypatch.setattr("src.phase2.wizard_walkthrough.time.sleep", lambda _seconds: None)

    client = FakeAdbClient(
        ui_dumps=[SCREEN_WITHOUT_WIZ_NEXT_XML, FULL_SCREEN_XML],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
        connected=True,
    )
    slot = Slot("slot-2", client, max_retry=3)

    result = slot.run_init_apn(_profile(), NETWORK_CONFIG)

    assert result is True
    assert slot.state == SlotState.LOGIN_INSTALL
    # Two dumps were consumed for the retried step (miss, then hit).
    dump_calls = [c for c in client.shell_calls if c.startswith("uiautomator dump")]
    assert len(dump_calls) >= 2


def test_run_init_apn_not_connected_fails_with_reason():
    client = FakeAdbClient(connected=False)
    slot = Slot("slot-3", client, max_retry=3)

    result = slot.run_init_apn(_profile(), NETWORK_CONFIG)

    assert result is False
    assert slot.state == SlotState.FAILED
    assert "not connected" in slot.last_error


def test_run_slot_with_retries_escalates_past_max_retry():
    # is_connected() always False -> run_init_apn fails deterministically and
    # fast every attempt, with no sleeps involved.
    client = FakeAdbClient(connected=False)
    slot = Slot("slot-4", client, max_retry=2)

    final_state = run_slot_with_retries(slot, _profile(), NETWORK_CONFIG)

    assert final_state == SlotState.ESCALATED
    assert slot.state == SlotState.ESCALATED
    assert slot.retry_count == slot.max_retry + 1
    assert slot.last_error is not None


def test_run_slot_with_retries_succeeds_without_reaching_escalation():
    client = FakeAdbClient(
        ui_dumps=[FULL_SCREEN_XML],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
        connected=True,
    )
    slot = Slot("slot-5", client, max_retry=3)

    final_state = run_slot_with_retries(slot, _profile(), NETWORK_CONFIG)

    assert final_state == SlotState.LOGIN_INSTALL
    assert slot.retry_count == 0


def test_run_slot_with_retries_recovers_after_a_transient_failure(monkeypatch):
    """A slot that fails once (e.g. shell hiccup while checking dumpsys) but
    would succeed on the immediate next attempt should end up LOGIN_INSTALL,
    not ESCALATED, and retry_count should reflect the one failed attempt."""

    calls = {"n": 0}

    def flaky_is_connected(self):
        calls["n"] += 1
        if calls["n"] == 1:
            return False  # first attempt: device not yet "connected"
        return True

    monkeypatch.setattr(FakeAdbClient, "is_connected", flaky_is_connected)

    client = FakeAdbClient(
        ui_dumps=[FULL_SCREEN_XML],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    slot = Slot("slot-6", client, max_retry=3)

    final_state = run_slot_with_retries(slot, _profile(), NETWORK_CONFIG)

    assert final_state == SlotState.LOGIN_INSTALL
    assert slot.retry_count == 1


def test_run_slot_with_retries_forwards_skip_wizard():
    """main_phase2.py --skip-wizard flows through run_slot_with_retries()
    down to Slot.run_init_apn() — a home-screen dump with no wizard
    elements at all must still succeed when skip_wizard=True."""
    home_screen_xml = """<hierarchy>
  <node text="Settings" bounds="[0,200][100,300]" />
  <node text="Network" bounds="[0,300][100,400]" />
  <node resource-id="apn:name" bounds="[0,400][100,500]" />
  <node resource-id="apn:apn" bounds="[0,500][100,600]" />
  <node resource-id="apn:save" bounds="[0,600][100,700]" />
</hierarchy>"""
    client = FakeAdbClient(
        ui_dumps=[home_screen_xml],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    slot = Slot("slot-7", client, max_retry=3)

    final_state = run_slot_with_retries(slot, _profile(), NETWORK_CONFIG, skip_wizard=True)

    assert final_state == SlotState.LOGIN_INSTALL
    assert slot.retry_count == 0
