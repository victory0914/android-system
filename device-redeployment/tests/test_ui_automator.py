"""Tests for src/device/ui_automator.py.

Fixtures are hand-written XML strings that follow the real `uiautomator dump`
schema (<hierarchy><node resource-id="..." bounds="[x1,y1][x2,y2]"
text="..." class="..." .../></hierarchy>) even though the specific
resource-id values are invented (Stage A — see
PENDING_REAL_DEVICE_DATA.md).
"""

import pytest

from src.device.ui_automator import (
    AmbiguousResourceIdError,
    ForbiddenTapTargetError,
    HazardousScreenError,
    dump_ui,
    find_by_content_desc,
    find_by_text,
    find_resource_id,
    get_node_text,
    inject_text,
    input_text_direct,
    navigate_menu_path,
    node_is_checked,
    scroll_down,
    tap_by_content_desc,
    tap_by_text,
    tap_resource_id,
    wait_for_text_to_disappear,
)
from tests.fakes import FakeAdbClient

# Fixture 1: a simple screen with unique resource-ids (a wizard "Next" button).
SIMPLE_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="Select your language" resource-id="com.google.android.setupwizard:id/title"
          class="android.widget.TextView" bounds="[40,120][1040,220]" />
    <node index="1" text="Next" resource-id="com.google.android.setupwizard:id/next_button"
          class="android.widget.Button" bounds="[820,1980][1040,2080]" />
  </node>
</hierarchy>
"""

# Fixture 2: a list-type screen (modeled on the Wi-Fi network list) with
# multiple nodes sharing one resource-id, distinguished only by `text`. This
# is the more important fixture — it's standing in for the specific risk
# already identified before ever seeing a real device: silently tapping the
# wrong list row.
WIFI_LIST_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="HomeNetwork_5G" resource-id="com.android.settings:id/wifi_network_list"
          class="android.widget.TextView" bounds="[40,300][1040,400]" />
    <node index="1" text="HomeNetwork_2G" resource-id="com.android.settings:id/wifi_network_list"
          class="android.widget.TextView" bounds="[40,410][1040,510]" />
    <node index="2" text="Neighbor_WiFi" resource-id="com.android.settings:id/wifi_network_list"
          class="android.widget.TextView" bounds="[40,520][1040,620]" />
  </node>
</hierarchy>
"""

NO_MATCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]" />
</hierarchy>
"""


def test_find_resource_id_unique_match_returns_center_coords():
    coords = find_resource_id(
        SIMPLE_SCREEN_XML, "com.google.android.setupwizard:id/next_button"
    )
    assert coords == ((820 + 1040) // 2, (1980 + 2080) // 2)


def test_find_resource_id_no_match_returns_none():
    coords = find_resource_id(NO_MATCH_XML, "com.google.android.setupwizard:id/next_button")
    assert coords is None


def test_find_resource_id_ambiguous_without_disambiguator_raises():
    with pytest.raises(AmbiguousResourceIdError):
        find_resource_id(WIFI_LIST_SCREEN_XML, "com.android.settings:id/wifi_network_list")


def test_find_resource_id_disambiguates_by_text():
    coords = find_resource_id(
        WIFI_LIST_SCREEN_XML,
        "com.android.settings:id/wifi_network_list",
        text="Neighbor_WiFi",
    )
    assert coords == ((40 + 1040) // 2, (520 + 620) // 2)


def test_find_resource_id_text_no_match_returns_none():
    coords = find_resource_id(
        WIFI_LIST_SCREEN_XML,
        "com.android.settings:id/wifi_network_list",
        text="DoesNotExist",
    )
    assert coords is None


def test_find_resource_id_disambiguates_by_index():
    first = find_resource_id(
        WIFI_LIST_SCREEN_XML, "com.android.settings:id/wifi_network_list", index=1
    )
    second = find_resource_id(
        WIFI_LIST_SCREEN_XML, "com.android.settings:id/wifi_network_list", index=2
    )
    assert first == ((40 + 1040) // 2, (410 + 510) // 2)
    assert second == ((40 + 1040) // 2, (520 + 620) // 2)


def test_find_resource_id_index_out_of_range_returns_none():
    coords = find_resource_id(
        WIFI_LIST_SCREEN_XML, "com.android.settings:id/wifi_network_list", index=99
    )
    assert coords is None


def test_dump_ui_returns_pulled_xml():
    client = FakeAdbClient(ui_dumps=[SIMPLE_SCREEN_XML])
    xml = dump_ui(client)
    assert xml == SIMPLE_SCREEN_XML
    assert any(call.startswith("uiautomator dump") for call in client.shell_calls)
    assert any(call.startswith("rm -f") for call in client.shell_calls)


def test_tap_resource_id_taps_center_when_found():
    client = FakeAdbClient(ui_dumps=[SIMPLE_SCREEN_XML])
    result = tap_resource_id(
        client, "com.google.android.setupwizard:id/next_button"
    )
    assert result is True
    expected_x, expected_y = (820 + 1040) // 2, (1980 + 2080) // 2
    assert f"input tap {expected_x} {expected_y}" in client.shell_calls


def test_tap_resource_id_returns_false_when_not_found():
    client = FakeAdbClient(ui_dumps=[NO_MATCH_XML])
    result = tap_resource_id(client, "com.google.android.setupwizard:id/next_button")
    assert result is False
    assert not any(call.startswith("input tap") for call in client.shell_calls)


def test_tap_resource_id_propagates_ambiguous_error():
    client = FakeAdbClient(ui_dumps=[WIFI_LIST_SCREEN_XML])
    with pytest.raises(AmbiguousResourceIdError):
        tap_resource_id(client, "com.android.settings:id/wifi_network_list")


def test_inject_text_sends_broadcast():
    client = FakeAdbClient()
    result = inject_text(client, "hello world")
    assert result is True
    assert any("ADB_INPUT_TEXT" in call and "hello world" in call for call in client.shell_calls)


# --- Stage B additions below ------------------------------------------------
# Real SHG10 dumps (tests/fixtures/*_SHG10.xml, see docs/record.md) showed
# that list rows share one generic resource-id (`android:id/title`) and that
# icon-only controls (overflow menu, "navigate up") have neither a
# resource-id nor visible text — only a content-desc. These tests cover the
# infra added to handle that, using hand-written fixtures (the real-XML
# fixtures are exercised separately in the SHG10-specific tests below).

CONTENT_DESC_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="" resource-id="" content-desc="More options"
          class="android.widget.ImageButton" bounds="[969,83][1080,215]" />
    <node index="1" text="" resource-id="" content-desc="Navigate up"
          class="android.widget.ImageButton" bounds="[0,72][154,226]" />
  </node>
</hierarchy>
"""

SWITCH_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="" resource-id="android:id/switch_widget" checked="true"
          class="android.widget.Switch" bounds="[882,1034][1036,1166]" />
  </node>
</hierarchy>
"""

HAZARD_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="USBデバッグが接続されました" resource-id=""
          class="android.widget.TextView" bounds="[0,0][1080,100]" />
    <node index="1" text="無効にするにはここをタップしてください" resource-id=""
          class="android.widget.TextView" bounds="[0,100][1080,200]" />
    <node index="2" text="Next" resource-id="wiz:next"
          class="android.widget.Button" bounds="[820,1980][1040,2080]" />
  </node>
</hierarchy>
"""

SPINNER_THEN_GONE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="キャリア設定中" resource-id="" class="android.widget.TextView" bounds="[0,0][1080,200]" />
</hierarchy>
"""

HOME_SCREEN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="Home" resource-id="" class="android.widget.TextView" bounds="[0,0][1080,200]" />
</hierarchy>
"""


def test_find_by_content_desc_disambiguates():
    coords = find_by_content_desc(CONTENT_DESC_SCREEN_XML, "More options")
    assert coords == ((969 + 1080) // 2, (83 + 215) // 2)


def test_find_by_content_desc_no_match_returns_none():
    assert find_by_content_desc(CONTENT_DESC_SCREEN_XML, "Nonexistent") is None


def test_tap_by_content_desc_taps_center():
    client = FakeAdbClient(ui_dumps=[CONTENT_DESC_SCREEN_XML])
    result = tap_by_content_desc(client, "Navigate up")
    assert result is True
    expected_x, expected_y = (0 + 154) // 2, (72 + 226) // 2
    assert f"input tap {expected_x} {expected_y}" in client.shell_calls


def test_node_is_checked_true_and_false():
    assert node_is_checked(SWITCH_SCREEN_XML, "android:id/switch_widget") is True
    off_xml = SWITCH_SCREEN_XML.replace('checked="true"', 'checked="false"')
    assert node_is_checked(off_xml, "android:id/switch_widget") is False


def test_node_is_checked_no_match_returns_none():
    assert node_is_checked(SWITCH_SCREEN_XML, "android:id/does_not_exist") is None


def test_tap_by_text_refuses_forbidden_targets():
    client = FakeAdbClient(ui_dumps=[SIMPLE_SCREEN_XML])
    with pytest.raises(ForbiddenTapTargetError):
        tap_by_text(client, "戻る")
    with pytest.raises(ForbiddenTapTargetError):
        tap_by_text(client, "中断し、リマインダーを受け取る")
    assert not any(call.startswith("input tap") for call in client.shell_calls)


def test_tap_resource_id_refuses_on_hazardous_screen():
    client = FakeAdbClient(ui_dumps=[HAZARD_SCREEN_XML])
    with pytest.raises(HazardousScreenError):
        tap_resource_id(client, "wiz:next")
    assert not any(call.startswith("input tap") for call in client.shell_calls)


def test_tap_by_text_refuses_on_hazardous_screen():
    client = FakeAdbClient(ui_dumps=[HAZARD_SCREEN_XML])
    with pytest.raises(HazardousScreenError):
        tap_by_text(client, "Next")
    assert not any(call.startswith("input tap") for call in client.shell_calls)


def test_tap_by_content_desc_refuses_on_hazardous_screen():
    client = FakeAdbClient(ui_dumps=[HAZARD_SCREEN_XML])
    with pytest.raises(HazardousScreenError):
        tap_by_content_desc(client, "anything")
    assert not any(call.startswith("input tap") for call in client.shell_calls)


def test_scroll_down_computes_swipe_from_dumped_bounds():
    client = FakeAdbClient(ui_dumps=[SIMPLE_SCREEN_XML])  # root bounds [0,0][1080,2160]
    scroll_down(client, duration_ms=250)
    expected = f"input swipe 540 {int(2160 * 0.8)} 540 {int(2160 * 0.2)} 250"
    assert expected in client.shell_calls


def test_wait_for_text_to_disappear_returns_true_once_gone():
    client = FakeAdbClient(ui_dumps=[SPINNER_THEN_GONE_XML, HOME_SCREEN_XML])
    result = wait_for_text_to_disappear(
        client, "キャリア設定中", timeout_seconds=5, poll_interval_seconds=0
    )
    assert result is True


def test_wait_for_text_to_disappear_returns_false_at_timeout():
    client = FakeAdbClient(ui_dumps=[SPINNER_THEN_GONE_XML])
    result = wait_for_text_to_disappear(
        client, "キャリア設定中", timeout_seconds=0, poll_interval_seconds=0
    )
    assert result is False


def test_navigate_menu_path_mixed_step_types():
    combined_xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="Settings" resource-id="" bounds="[0,0][200,100]" />
    <node index="1" text="" resource-id="" content-desc="gear"
          class="android.widget.ImageView" bounds="[0,100][200,200]" />
    <node index="2" text="" resource-id="apn:menu" bounds="[0,200][200,300]" />
  </node>
</hierarchy>
"""
    client = FakeAdbClient(ui_dumps=[combined_xml])
    steps = [
        {"type": "text", "value": "Settings"},
        {"type": "content_desc", "value": "gear"},
        {"type": "resource_id", "value": "apn:menu"},
    ]
    result = navigate_menu_path(client, steps)
    assert result is True
    tap_calls = [c for c in client.shell_calls if c.startswith("input tap")]
    assert len(tap_calls) == 3


def test_navigate_menu_path_stops_on_first_missing_step():
    client = FakeAdbClient(ui_dumps=[NO_MATCH_XML])
    steps = [{"type": "text", "value": "Does Not Exist"}, {"type": "text", "value": "Unreachable"}]
    result = navigate_menu_path(client, steps)
    assert result is False


def test_navigate_menu_path_unknown_step_type_raises():
    client = FakeAdbClient(ui_dumps=[NO_MATCH_XML])
    with pytest.raises(ValueError):
        navigate_menu_path(client, [{"type": "bogus", "value": "x"}])


def test_navigate_menu_path_accepts_legacy_plain_string_steps():
    """The 3 models not yet updated with real navigation data still use a
    flat list of strings for menu_path (Stage A shape) — must keep working."""
    legacy_xml = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2160]">
    <node index="0" text="Settings" resource-id="" bounds="[0,0][200,100]" />
    <node index="1" text="Network &amp; internet" resource-id="" bounds="[0,100][200,200]" />
  </node>
</hierarchy>
"""
    client = FakeAdbClient(ui_dumps=[legacy_xml])
    result = navigate_menu_path(client, ["Settings", "Network & internet"])
    assert result is True


# --- Stage B (SHG10 real APN-save session, 2026-09-08) additions ----------

VALIDATION_DIALOG_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2432]">
    <node index="0" text="MCC欄は3桁で指定してください。" resource-id="android:id/message"
          class="android.widget.TextView" bounds="[71,1117][1009,1176]" />
    <node index="1" text="OK" resource-id="android:id/button1"
          class="android.widget.Button" bounds="[800,1210][976,1359]" />
  </node>
</hierarchy>
"""


def test_get_node_text_returns_matched_text():
    assert get_node_text(VALIDATION_DIALOG_XML, "android:id/message") == "MCC欄は3桁で指定してください。"
    assert get_node_text(VALIDATION_DIALOG_XML, "android:id/button1") == "OK"


def test_get_node_text_no_match_returns_none():
    assert get_node_text(VALIDATION_DIALOG_XML, "android:id/does_not_exist") is None


def test_input_text_direct_uses_input_text_command():
    client = FakeAdbClient()
    result = input_text_direct(client, "440")
    assert result is True
    assert 'input text "440"' in client.shell_calls


def test_input_text_direct_escapes_spaces():
    client = FakeAdbClient()
    input_text_direct(client, "a b")
    assert 'input text "a%sb"' in client.shell_calls


def test_input_text_direct_escapes_shell_special_characters():
    """Passwords routinely contain these — matters more here than for the
    original MCC/MNC use case (pure digits)."""
    client = FakeAdbClient()
    input_text_direct(client, 'P@ss"w$ord`!\\')
    assert 'input text "P@ss\\"w\\$ord\\`!\\\\"' in client.shell_calls
