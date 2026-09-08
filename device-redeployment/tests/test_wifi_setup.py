"""Tests for src/phase2/wifi_setup.py — in particular the Stage B fix for
blindly tapping the Wi-Fi toggle (a real SHG10 capture showed it's a Switch
with a `checked` state that must be read first, not assumed) and the new
menu_path navigation step."""

from src.device.model_profile import ModelProfile
from src.phase2.wifi_setup import connect_wifi
from tests.fakes import FakeAdbClient

PROFILE_WITH_MENU_PATH = ModelProfile(
    {
        "model": "Test",
        "model_number": "TST01",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {
            "menu_path": [
                {"type": "text", "value": "設定"},
                {"type": "text", "value": "ネットワークとインターネット"},
            ],
            "toggle_resource_id": "android:id/switch_widget",
            "network_list_resource_id": "android:id/title",
        },
        "apn_settings": {"menu_path": ["Settings"]},
    }
)

PROFILE_NO_MENU_PATH = ModelProfile(
    {
        "model": "Test",
        "model_number": "TST02",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {
            "toggle_resource_id": "android:id/switch_widget",
            "network_list_resource_id": "android:id/title",
        },
        "apn_settings": {"menu_path": ["Settings"]},
    }
)

TOGGLE_ON_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="" resource-id="android:id/switch_widget" checked="true"
          class="android.widget.Switch" bounds="[882,1034][1036,1166]" />
    <node index="1" text="TestSSID" resource-id="android:id/title"
          class="android.widget.TextView" bounds="[40,1200][1040,1300]" />
  </node>
</hierarchy>
"""

TOGGLE_OFF_SCREEN_XML = TOGGLE_ON_SCREEN_XML.replace('checked="true"', 'checked="false"')

MENU_THEN_TOGGLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="設定" resource-id="" bounds="[0,0][200,100]" />
    <node index="1" text="ネットワークとインターネット" resource-id="" bounds="[0,100][200,200]" />
    <node index="2" text="" resource-id="android:id/switch_widget" checked="true"
          class="android.widget.Switch" bounds="[882,1034][1036,1166]" />
    <node index="3" text="TestSSID" resource-id="android:id/title"
          class="android.widget.TextView" bounds="[40,1200][1040,1300]" />
  </node>
</hierarchy>
"""

DUMPSYS_WIFI_CONNECTED = 'SSID: "TestSSID", state: COMPLETED'


def _shell_fails_connect_network():
    """shell_failures needs the exact command string; connect_wifi escapes
    quotes but ssid/password below have none, so this is the literal command."""
    return {'cmd wifi connect-network "TestSSID" wpa2 "hunter2"'}


def test_ui_fallback_does_not_tap_toggle_when_already_on():
    client = FakeAdbClient(
        ui_dumps=[TOGGLE_ON_SCREEN_XML],
        shell_failures=_shell_fails_connect_network(),
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    result = connect_wifi(
        client, PROFILE_NO_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    assert result is True
    toggle_tap = "input tap {} {}".format((882 + 1036) // 2, (1034 + 1166) // 2)
    assert toggle_tap not in client.shell_calls


def test_ui_fallback_taps_toggle_when_off():
    client = FakeAdbClient(
        ui_dumps=[TOGGLE_OFF_SCREEN_XML, TOGGLE_ON_SCREEN_XML],
        shell_failures=_shell_fails_connect_network(),
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    connect_wifi(
        client, PROFILE_NO_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    toggle_tap = "input tap {} {}".format((882 + 1036) // 2, (1034 + 1166) // 2)
    assert toggle_tap in client.shell_calls


def test_ui_fallback_navigates_menu_path_before_toggle_and_list():
    client = FakeAdbClient(
        ui_dumps=[MENU_THEN_TOGGLE_XML, MENU_THEN_TOGGLE_XML, MENU_THEN_TOGGLE_XML],
        shell_failures=_shell_fails_connect_network(),
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    result = connect_wifi(
        client, PROFILE_WITH_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    assert result is True
    tap_calls = [c for c in client.shell_calls if c.startswith("input tap")]
    # menu step 1 ("設定"), menu step 2 ("ネットワークとインターネット"), then the
    # SSID row (toggle already on, not tapped) — at least these 3 taps happened,
    # in that relative order.
    settings_tap = "input tap {} {}".format((0 + 200) // 2, (0 + 100) // 2)
    menu_step2_tap = "input tap {} {}".format((0 + 200) // 2, (100 + 200) // 2)
    assert settings_tap in tap_calls
    assert menu_step2_tap in tap_calls
    assert tap_calls.index(settings_tap) < tap_calls.index(menu_step2_tap)


def test_ui_fallback_stops_if_menu_path_navigation_fails():
    client = FakeAdbClient(
        ui_dumps=["<hierarchy><node bounds=\"[0,0][100,100]\" /></hierarchy>"],
        shell_failures=_shell_fails_connect_network(),
    )
    result = connect_wifi(
        client, PROFILE_WITH_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=0, poll_interval_seconds=0,
    )
    assert result is False
