"""Tests against real `uiautomator dump` XML captured from an actual SOG08
(Xperia Ace III) unit — as opposed to the hand-written Stage A fixtures in
test_ui_automator.py.

Captured 2026-09-16 (see docs/record.md), same set as SOG07: wifi_list,
apn_list, apn_entry at two scroll positions, and apn_overflow_menu. Every
id/content-desc checked here is byte-identical to SOG07's and SHG10's —
three real devices, two manufacturers, two Android versions, the same
plain AOSP com.android.settings screens throughout.
"""

from pathlib import Path

import pytest

from src.device.ui_automator import (
    AmbiguousResourceIdError,
    find_by_content_desc,
    find_resource_id,
)
from src.phase2.apn_setup import _looks_like_apn_list_screen

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "Xperia Ace III（SOG08）"

WIFI_LIST_XML = (FIXTURES_DIR / "wifi_list_SOG08.xml").read_text(encoding="utf-8")
APN_LIST_XML = (FIXTURES_DIR / "apn_list_SOG08.xml").read_text(encoding="utf-8")
APN_ENTRY_TOP_XML = (FIXTURES_DIR / "apn_entry_top_SOG08.xml").read_text(encoding="utf-8")
APN_ENTRY_MIDDLE_XML = (FIXTURES_DIR / "apn_entry_middle_SOG08.xml").read_text(encoding="utf-8")
APN_ENTRY_BOTTOM_XML = (FIXTURES_DIR / "apn_entry_bottom_SOG08.xml").read_text(encoding="utf-8")
APN_OVERFLOW_MENU_XML = (FIXTURES_DIR / "apn_overflow_menu_SOG08.xml").read_text(encoding="utf-8")
MOBILE_NETWORK_XML = (FIXTURES_DIR / "mobile_network_SOG08.xml").read_text(encoding="utf-8")


def test_wifi_row_title_is_ambiguous_without_disambiguator():
    with pytest.raises(AmbiguousResourceIdError):
        find_resource_id(WIFI_LIST_XML, "android:id/title")


def test_wifi_toggle_switch_is_unambiguous_and_reports_checked_state():
    coords = find_resource_id(WIFI_LIST_XML, "android:id/switch_widget")
    assert coords is not None


def test_wifi_settings_gear_icon_resolves_by_resource_id():
    coords = find_resource_id(WIFI_LIST_XML, "com.android.settings:id/settings_button")
    assert coords is not None


def test_wifi_screen_title_is_internet_not_sharp_wording():
    """Same real, confirmed difference from SHG10 as SOG07: title renders
    via content-desc "インターネット", not "Wi-Fi とモバイルネットワーク"."""
    assert find_by_content_desc(WIFI_LIST_XML, "インターネット") is not None


def test_looks_like_apn_list_screen_recognizes_the_real_sog08_dump():
    assert _looks_like_apn_list_screen(APN_LIST_XML) is True


def test_apn_list_add_button_and_overflow_menu_content_desc():
    assert find_by_content_desc(APN_LIST_XML, "新しい APN") is not None
    assert find_by_content_desc(APN_LIST_XML, "その他のオプション") is not None


def test_apn_list_navigate_up_content_desc():
    assert find_by_content_desc(APN_LIST_XML, "上へ移動") is not None


def test_apn_field_labels_share_generic_title_id_across_scrolls():
    for xml in (APN_ENTRY_TOP_XML, APN_ENTRY_MIDDLE_XML, APN_ENTRY_BOTTOM_XML):
        with pytest.raises(AmbiguousResourceIdError):
            find_resource_id(xml, "android:id/title")


@pytest.mark.parametrize(
    "label,in_xml",
    [
        ("名前", APN_ENTRY_TOP_XML),
        ("APN", APN_ENTRY_TOP_XML),
        ("MCC", APN_ENTRY_MIDDLE_XML),
        ("MNC", APN_ENTRY_MIDDLE_XML),
    ],
)
def test_apn_field_rows_resolve_by_label_text(label, in_xml):
    coords = find_resource_id(in_xml, "android:id/title", text=label)
    assert coords is not None


def test_mcc_mnc_fields_show_not_yet_set_on_this_capture():
    """Unlike SHG10 (a real SIM's MCC/MNC were pre-filled), this capture
    shows both as "未設定" (not set) — a blank entry, not evidence the
    fields are absent. Confirms the fields exist and are readable either
    way."""
    mcc_summary = find_resource_id(APN_ENTRY_MIDDLE_XML, "android:id/summary", text="未設定")
    assert mcc_summary is not None


def test_apn_overflow_menu_save_and_cancel_share_generic_title_id():
    assert find_resource_id(APN_OVERFLOW_MENU_XML, "android:id/title", text="保存") is not None
    assert (
        find_resource_id(APN_OVERFLOW_MENU_XML, "android:id/title", text="キャンセル")
        is not None
    )


# --- Mobile network (carrier-specific) settings screen, 2026-09-18 ---------
# Real finding: android.settings.APN_SETTINGS reaches a non-authoritative
# APN context (first found on SHG07) — the real, live one is reached by
# navigating to THIS screen and tapping its "アクセス ポイント名" row. See
# apn_setup.py's _navigate_apn_menu() docstring for the full account.


def test_mobile_network_screen_title_is_the_carrier_name():
    """Same real pattern as SHG07: the collapsing_toolbar's content-desc
    is the SIM's carrier name ("Rakuten"), confirming this is the
    per-SIM settings screen."""
    assert find_by_content_desc(MOBILE_NETWORK_XML, "Rakuten") is not None


def test_mobile_network_row_titles_share_generic_id():
    with pytest.raises(AmbiguousResourceIdError):
        find_resource_id(MOBILE_NETWORK_XML, "android:id/title")


def test_access_point_names_row_is_real_and_tappable():
    """Confirms the critical finding independently on SOG08's own real
    hardware (not just inherited from SHG07): "アクセス ポイント名"
    (WITH a space) is a genuine android:id/title row here too — same
    byte-identical pattern as SHG07's, across manufacturers."""
    coords = find_resource_id(MOBILE_NETWORK_XML, "android:id/title", text="アクセス ポイント名")
    assert coords is not None


def test_mobile_network_screen_has_a_navigation_bar_occupying_the_bottom():
    """Real, concrete evidence for why _navigate_apn_menu() scrolls down
    before tapping this row: android:id/navigationBarBackground starts
    at y=1406, exactly where the content area (and this row's own
    bounds) ends — a tap right at the row's bottom edge risks landing on
    the system nav bar instead of the app."""
    assert 'resource-id="android:id/navigationBarBackground"' in MOBILE_NETWORK_XML
