"""End-to-end smoke test: the *real* SHG10 model YAML (config/models/
sharp_aquos_sense7.yaml, Stage B data) driven through Slot.run_init_apn().

This deliberately does NOT expect a full success — two wizard screens
(welcome, software_update) have genuinely unverified button labels
(TODO(verify-on-device) placeholders, per docs/record.md), so the flow must
fail loudly right there rather than guess or silently proceed. That's the
correct, intended behavior for this model in its current state, and this
test is a regression guard for it: it would be a real bug if the TODO
placeholder ever accidentally matched something and let automation tap the
wrong thing.
"""

from pathlib import Path

from src.device.model_profile import ModelProfile
from src.orchestration.slot import Slot, SlotState
from tests.fakes import FakeAdbClient

REPO_ROOT = Path(__file__).resolve().parent.parent
SHG10_YAML = REPO_ROOT / "config" / "models" / "sharp_aquos_sense7.yaml"

WELCOME_SCREEN_XML = """<hierarchy>
  <node text="ようこそ" bounds="[0,0][200,100]" />
</hierarchy>"""

NETWORK_CONFIG = {
    "wifi": {"ssid": "ARIZASU-WiFi-6F_5G", "password": "hunter2"},
    "apn": {"apn_name": "rakuten.jp", "mcc": "440", "mnc": "11"},
}


def test_real_shg10_profile_loads_and_fails_loudly_at_unverified_wizard_screen():
    profile = ModelProfile.load(str(SHG10_YAML))
    client = FakeAdbClient(ui_dumps=[WELCOME_SCREEN_XML], connected=True)
    slot = Slot("integration-slot", client, max_retry=0)

    result = slot.run_init_apn(profile, NETWORK_CONFIG)

    assert result is False
    assert slot.state == SlotState.FAILED
    # Must fail at the wizard step specifically, not proceed past it.
    assert "wizard" in slot.last_error.lower()
    # Must never have tapped anything — no target was ever confirmed found.
    assert not any(c.startswith("input tap") for c in client.shell_calls)
