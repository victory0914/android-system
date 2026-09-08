"""Tests for src/phase2/wifi_setup.py — in particular the Stage B fix for
blindly tapping the Wi-Fi toggle (a real SHG10 capture showed it's a Switch
with a `checked` state that must be read first, not assumed), menu_path
navigation, and the android.settings.WIFI_SETTINGS intent shortcut added
after a real client-PC run showed menu_path text navigation (tapping "設定")
fails whenever the device isn't already sitting on a screen where that text
is visible — e.g. the home screen, reached via --skip-wizard testing."""

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
    # 1st dump: WIFI_SETTINGS-intent landing check (toggle present -> menu_path
    # skipped). 2nd: toggle state check (off). 3rd (repeats): toggle tap's own
    # dump + the SSID list tap afterward.
    client = FakeAdbClient(
        ui_dumps=[TOGGLE_OFF_SCREEN_XML, TOGGLE_OFF_SCREEN_XML, TOGGLE_ON_SCREEN_XML],
        shell_failures=_shell_fails_connect_network(),
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    connect_wifi(
        client, PROFILE_NO_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    toggle_tap = "input tap {} {}".format((882 + 1036) // 2, (1034 + 1166) // 2)
    assert toggle_tap in client.shell_calls


def test_ui_fallback_skips_menu_path_when_wifi_settings_intent_lands_correctly():
    """The android.settings.WIFI_SETTINGS intent, when it lands somewhere
    showing the configured toggle, should make menu_path navigation
    unnecessary entirely — no "設定" tap should happen."""
    client = FakeAdbClient(
        ui_dumps=[TOGGLE_ON_SCREEN_XML],
        shell_failures=_shell_fails_connect_network(),
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    result = connect_wifi(
        client, PROFILE_WITH_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    assert result is True
    assert any(c == "am start -a android.settings.WIFI_SETTINGS" for c in client.shell_calls)
    settings_tap = "input tap {} {}".format((0 + 200) // 2, (0 + 100) // 2)
    assert settings_tap not in client.shell_calls


def test_ui_fallback_falls_back_to_menu_path_when_intent_command_fails():
    """If the WIFI_SETTINGS intent itself fails (e.g. blocked on a
    locked-down OEM build), menu_path navigation must still be tried —
    exactly Stage A's original fallback behavior."""
    client = FakeAdbClient(
        ui_dumps=[MENU_THEN_TOGGLE_XML],
        shell_failures=_shell_fails_connect_network()
        | {"am start -a android.settings.WIFI_SETTINGS"},
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    result = connect_wifi(
        client, PROFILE_WITH_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    assert result is True
    settings_tap = "input tap {} {}".format((0 + 200) // 2, (0 + 100) // 2)
    assert settings_tap in client.shell_calls


def test_ui_fallback_falls_back_to_menu_path_when_intent_lands_elsewhere():
    """If the intent runs without error but doesn't land somewhere showing
    the configured toggle (e.g. it silently no-oped, or landed on an
    unrelated screen), menu_path navigation must still be tried rather than
    assuming the intent worked."""
    client = FakeAdbClient(
        # 1st dump: intent-landing check — no toggle here, so it must fall
        # back. 2nd+ (repeats): the actual navigable screen.
        ui_dumps=["<hierarchy><node text=\"Home\" bounds=\"[0,0][10,10]\" /></hierarchy>", MENU_THEN_TOGGLE_XML],
        shell_failures=_shell_fails_connect_network(),
        shell_responses={"dumpsys wifi": DUMPSYS_WIFI_CONNECTED},
    )
    result = connect_wifi(
        client, PROFILE_WITH_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=1, poll_interval_seconds=0,
    )
    assert result is True
    tap_calls = [c for c in client.shell_calls if c.startswith("input tap")]
    settings_tap = "input tap {} {}".format((0 + 200) // 2, (0 + 100) // 2)
    menu_step2_tap = "input tap {} {}".format((0 + 200) // 2, (100 + 200) // 2)
    assert settings_tap in tap_calls
    assert menu_step2_tap in tap_calls
    assert tap_calls.index(settings_tap) < tap_calls.index(menu_step2_tap)


def test_ui_fallback_stops_if_both_intent_and_menu_path_fail():
    client = FakeAdbClient(
        ui_dumps=["<hierarchy><node bounds=\"[0,0][100,100]\" /></hierarchy>"],
        shell_failures=_shell_fails_connect_network(),
    )
    result = connect_wifi(
        client, PROFILE_WITH_MENU_PATH, "TestSSID", "hunter2",
        poll_timeout_seconds=0, poll_interval_seconds=0,
    )
    assert result is False
