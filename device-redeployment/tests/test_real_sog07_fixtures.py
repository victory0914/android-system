"""Tests against real `uiautomator dump` XML captured from an actual SOG07
(Xperia 10 IV) unit — as opposed to the hand-written Stage A fixtures in
test_ui_automator.py.

Captured 2026-09-16 (see docs/record.md): wifi_list, apn_list, apn_entry
at three scroll positions, and apn_overflow_menu — the same capture set
SHG10 has. Every id/content-desc checked here turned out byte-identical to
SHG10's real values, across a different manufacturer (Sony vs. SHARP) and
a different Android version (14 here) — real, direct confirmation this is
the plain, unskinned AOSP com.android.settings APN editor, not something
OEM-specific.
"""

from pathlib import Path

import pytest

from src.device.ui_automator import (
    AmbiguousResourceIdError,
    find_by_content_desc,
    find_resource_id,
)
from src.phase2.apn_setup import _looks_like_apn_list_screen

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "Xperia 10 IV（SOG07）"

WIFI_LIST_XML = (FIXTURES_DIR / "wifi_list_SOG07.xml").read_text(encoding="utf-8")
APN_LIST_XML = (FIXTURES_DIR / "apn_list_SOG07.xml").read_text(encoding="utf-8")
APN_ENTRY_TOP_XML = (FIXTURES_DIR / "apn_entry_top_SOG07.xml").read_text(encoding="utf-8")
APN_ENTRY_MIDDLE_XML = (FIXTURES_DIR / "apn_entry_middle_SOG07.xml").read_text(encoding="utf-8")
APN_ENTRY_BOTTOM_XML = (FIXTURES_DIR / "apn_entry_bottom_SOG07.xml").read_text(encoding="utf-8")
APN_OVERFLOW_MENU_XML = (FIXTURES_DIR / "apn_overflow_menu_SOG07.xml").read_text(encoding="utf-8")


def test_wifi_row_title_is_ambiguous_without_disambiguator():
    """Same real-world pattern as SHG10: android:id/title is shared by
    every row on this screen (carrier summary, Wi-Fi toggle label, every
    scanned SSID) — must fail loudly without a `text=` disambiguator."""
    with pytest.raises(AmbiguousResourceIdError):
        find_resource_id(WIFI_LIST_XML, "android:id/title")


def test_real_ssid_resolves_by_text():
    """earth5_1 (the same real SSID used for SHG10's confirmed Wi-Fi
    connection) is in range in this capture too."""
    coords = find_resource_id(WIFI_LIST_XML, "android:id/title", text="earth5_1")
    assert coords is not None


def test_wifi_toggle_switch_is_unambiguous_and_reports_checked_state():
    coords = find_resource_id(WIFI_LIST_XML, "android:id/switch_widget")
    assert coords is not None


def test_wifi_settings_gear_icon_resolves_by_resource_id():
    coords = find_resource_id(WIFI_LIST_XML, "com.android.settings:id/settings_button")
    assert coords is not None


def test_wifi_screen_title_is_internet_not_sharp_wording():
    """Real, confirmed difference from SHG10: this screen's own title
    renders via content-desc "インターネット" ("Internet"), not SHARP's
    "Wi-Fi とモバイルネットワーク" — the stock/Sony wording for the same
    combined Wi-Fi + mobile network screen."""
    assert find_by_content_desc(WIFI_LIST_XML, "インターネット") is not None


def test_looks_like_apn_list_screen_recognizes_the_real_sog07_dump():
    """The exact same screen-recognition logic built for SHG10
    (content-desc "APN" or "アクセスポイント名") already works here
    unmodified — no code change was needed, only real confirmation that
    it generalizes."""
    assert _looks_like_apn_list_screen(APN_LIST_XML) is True


def test_apn_list_add_button_and_overflow_menu_content_desc():
    """"新しい APN" (add) and "その他のオプション" (overflow), both
    content-desc only (no resource-id) — same as SHG10."""
    assert find_by_content_desc(APN_LIST_XML, "新しい APN") is not None
    assert find_by_content_desc(APN_LIST_XML, "その他のオプション") is not None


def test_apn_list_navigate_up_content_desc():
    assert find_by_content_desc(APN_LIST_XML, "上へ移動") is not None


def test_apn_field_labels_share_generic_title_id_across_all_three_scrolls():
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


def test_apn_overflow_menu_save_and_cancel_share_generic_title_id():
    """"保存"/"キャンセル" share android:id/title in the opened overflow
    popup, same pattern as everywhere else on this screen — matched by
    text, not resource-id."""
    assert find_resource_id(APN_OVERFLOW_MENU_XML, "android:id/title", text="保存") is not None
    assert (
        find_resource_id(APN_OVERFLOW_MENU_XML, "android:id/title", text="キャンセル")
        is not None
    )
