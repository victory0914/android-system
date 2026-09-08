"""Tests for src/orchestration/scheduler.py: run_phase2_batch() dispatch
across multiple fake slots in parallel, confirming one failing slot doesn't
block or crash the others."""

from src.device.model_profile import ModelProfile
from src.orchestration.scheduler import run_phase2_batch
from src.orchestration.slot import Slot, SlotState
from tests.fakes import FakeAdbClient

PROFILE_DATA = {
    "model": "Test Model",
    "model_number": "TST01",
    "manufacturer": "Test",
    "android_version": 13,
    "wizard_steps": [
        {"screen": "language_select", "resource_id": "wiz:next", "action": "tap"},
    ],
    "wifi_settings": {
        "toggle_resource_id": "wifi:toggle",
        "network_list_resource_id": "wifi:list",
    },
    "apn_settings": {
        "menu_path": ["Settings"],
        "name_field_resource_id": "apn:name",
        "apn_field_resource_id": "apn:apn",
        "save_button_resource_id": "apn:save",
    },
}

NETWORK_CONFIG = {
    "wifi": {"ssid": "TestSSID", "password": "hunter2"},
    "apn": {"apn_name": "internet", "mcc": "310", "mnc": "260"},
}

FULL_SCREEN_XML = """<hierarchy>
  <node resource-id="wiz:next" text="Next" bounds="[0,0][100,100]" />
  <node text="Settings" bounds="[0,200][100,300]" />
  <node resource-id="apn:name" bounds="[0,400][100,500]" />
  <node resource-id="apn:apn" bounds="[0,500][100,600]" />
  <node resource-id="apn:save" bounds="[0,600][100,700]" />
</hierarchy>"""

DUMPSYS_WIFI_CONNECTED = 'SSID: "TestSSID", state: COMPLETED'


def _profile() -> ModelProfile:
    return ModelProfile(dict(PROFILE_DATA))


def _successful_client() -> FakeAdbClient:
    return FakeAdbClient(
        ui_dumps=[FULL_SCREEN_XML],
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
        connected=True,
    )


def _always_failing_client() -> FakeAdbClient:
    # Never reports as connected -> run_init_apn fails immediately, every attempt.
    return FakeAdbClient(connected=False)


def test_run_phase2_batch_mixed_success_and_failure():
    slots = [
        Slot("slot-A", _successful_client(), max_retry=2),
        Slot("slot-B", _always_failing_client(), max_retry=1),
        Slot("slot-C", _successful_client(), max_retry=2),
    ]
    profile_map = {slot.slot_id: _profile() for slot in slots}

    results = run_phase2_batch(slots, profile_map, NETWORK_CONFIG, max_workers=3)

    assert results == {
        "slot-A": SlotState.LOGIN_INSTALL,
        "slot-B": SlotState.ESCALATED,
        "slot-C": SlotState.LOGIN_INSTALL,
    }
    # The failing slot exhausted its retries; the others weren't touched.
    slot_b = next(s for s in slots if s.slot_id == "slot-B")
    assert slot_b.retry_count == slot_b.max_retry + 1


def test_run_phase2_batch_all_slots_get_a_final_state():
    slots = [Slot(f"slot-{i}", _successful_client(), max_retry=1) for i in range(5)]
    profile_map = {slot.slot_id: _profile() for slot in slots}

    results = run_phase2_batch(slots, profile_map, NETWORK_CONFIG, max_workers=5)

    assert set(results.keys()) == {slot.slot_id for slot in slots}
    assert all(state == SlotState.LOGIN_INSTALL for state in results.values())


def test_run_phase2_batch_missing_profile_escalates_without_crashing_batch():
    good_slot = Slot("slot-good", _successful_client(), max_retry=1)
    orphan_slot = Slot("slot-orphan", _always_failing_client(), max_retry=1)
    slots = [good_slot, orphan_slot]

    # profile_map deliberately omits "slot-orphan".
    profile_map = {"slot-good": _profile()}

    results = run_phase2_batch(slots, profile_map, NETWORK_CONFIG, max_workers=2)

    assert results["slot-good"] == SlotState.LOGIN_INSTALL
    assert results["slot-orphan"] == SlotState.ESCALATED
    assert "profile_map" in orphan_slot.last_error or "ModelProfile" in orphan_slot.last_error


def test_run_phase2_batch_one_slot_raising_does_not_block_others(monkeypatch):
    """A slot whose client raises an unexpected exception (not just a normal
    False return) must not prevent the rest of the batch from completing."""

    class ExplodingClient(FakeAdbClient):
        def is_connected(self):
            raise RuntimeError("simulated hardware fault")

    slots = [
        Slot("slot-exploding", ExplodingClient(), max_retry=1),
        Slot("slot-fine", _successful_client(), max_retry=1),
    ]
    profile_map = {slot.slot_id: _profile() for slot in slots}

    results = run_phase2_batch(slots, profile_map, NETWORK_CONFIG, max_workers=2)

    assert results["slot-fine"] == SlotState.LOGIN_INSTALL
    assert results["slot-exploding"] == SlotState.ESCALATED
