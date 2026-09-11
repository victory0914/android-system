"""Tests against the real `uiautomator dump` XML captured from an actual
SHG10 unit (serial 352063910272451, see docs/record.md) — as opposed to the
hand-written Stage A fixtures in test_ui_automator.py.

These exercise the exact real-world disambiguation case the Stage A fixture
was standing in for: near-duplicate Wi-Fi SSIDs sharing one generic
resource-id (`android:id/title`), observed at the client site.
"""

from pathlib import Path

import pytest

from src.device.ui_automator import (
    AmbiguousResourceIdError,
    find_by_content_desc,
    find_by_text,
    find_resource_id,
    node_is_checked,
)
from src.phase2.apn_setup import _looks_like_apn_list_screen

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

WIFI_LIST_XML = (FIXTURES_DIR / "wifi_list_SHG10.xml").read_text(encoding="utf-8")
APN_ENTRY_TOP_XML = (FIXTURES_DIR / "apn_entry_top_SHG10.xml").read_text(encoding="utf-8")
APN_ENTRY_MIDDLE_XML = (FIXTURES_DIR / "apn_entry_middle_SHG10.xml").read_text(encoding="utf-8")
APN_ENTRY_BOTTOM_XML = (FIXTURES_DIR / "apn_entry_bottom_SHG10.xml").read_text(encoding="utf-8")
APN_RESTRICTED_XML = (FIXTURES_DIR / "apn_restricted_SHG10.xml").read_text(encoding="utf-8")

# Real near-duplicate SSID pairs observed at the client site (docs/record.md).
REAL_DUPLICATE_SSID_PAIRS = [
    ("ARIZASU-WiFi-6F_2.4GHz", "ARIZASU-WiFi-6F_5G"),
    ("SPWH_L13_72E834", "SPWH_L13_72E834_5G"),
]


def test_wifi_row_title_is_ambiguous_without_disambiguator():
    """`android:id/title` is shared by every row on this screen (the carrier
    summary row, the Wi-Fi toggle row's label, and every scanned SSID) — 9
    matches total. Without text/index, this must fail loudly rather than
    silently tap whichever row happens to come first."""
    with pytest.raises(AmbiguousResourceIdError):
        find_resource_id(WIFI_LIST_XML, "android:id/title")


@pytest.mark.parametrize("ssid_a,ssid_b", REAL_DUPLICATE_SSID_PAIRS)
def test_real_duplicate_ssid_pairs_disambiguate_correctly_by_text(ssid_a, ssid_b):
    coords_a = find_resource_id(WIFI_LIST_XML, "android:id/title", text=ssid_a)
    coords_b = find_resource_id(WIFI_LIST_XML, "android:id/title", text=ssid_b)

    assert coords_a is not None
    assert coords_b is not None
    # The two near-duplicate rows must resolve to two different tap targets —
    # this is exactly the failure mode (tapping the wrong one) the
    # disambiguation logic exists to prevent.
    assert coords_a != coords_b


def test_wifi_toggle_switch_is_unambiguous_and_reports_checked_state():
    # Real capture: exactly one android:id/switch_widget on this screen (the
    # Wi-Fi on/off toggle), currently ON.
    coords = find_resource_id(WIFI_LIST_XML, "android:id/switch_widget")
    assert coords is not None
    assert node_is_checked(WIFI_LIST_XML, "android:id/switch_widget") is True


def test_wifi_settings_gear_icon_resolves_by_resource_id():
    """The gear icon next to the carrier row (used to navigate to APN
    settings per docs/record.md) has an app-specific resource-id, unlike the
    generic android:id/title rows — resolvable directly, no disambiguation
    needed."""
    coords = find_resource_id(WIFI_LIST_XML, "com.android.settings:id/settings_button")
    assert coords is not None


def test_apn_field_labels_share_generic_title_id_across_all_three_scrolls():
    """None of the APN edit-form fields have a dedicated resource-id — they
    are all android:id/title, disambiguated only by their Japanese label
    text. This is true across all three scroll positions."""
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


def test_mcc_mnc_fields_exist_with_prefilled_values():
    """Settles the open question from docs/record.md: MCC/MNC fields DO
    exist on this build (visible once scrolled to the middle position, not
    in the top portion) and come pre-filled — 440/11, Japan/Rakuten
    Mobile's real MCC/MNC. `apn_settings.mcc_field_*`/`mnc_field_*` must NOT
    be deleted from the schema."""
    for xml in (APN_ENTRY_MIDDLE_XML, APN_ENTRY_BOTTOM_XML):
        mcc_row = find_resource_id(xml, "android:id/title", text="MCC")
        mnc_row = find_resource_id(xml, "android:id/title", text="MNC")
        assert mcc_row is not None
        assert mnc_row is not None


def test_overflow_and_navigate_up_buttons_have_no_resource_id_only_content_desc():
    """Both Save-action candidates (docs/record.md) are icon-only: no
    resource-id, no visible text, only a content-desc. Confirms why
    save_button_resource_id cannot be resolved to a resource-id from these
    dumps, and why find_by_content_desc() exists."""
    overflow = find_by_content_desc(APN_ENTRY_TOP_XML, "その他のオプション")
    navigate_up = find_by_content_desc(APN_ENTRY_TOP_XML, "上へ移動")
    assert overflow is not None
    assert navigate_up is not None


def test_add_new_apn_plus_icon_is_not_present_on_the_edit_form_dumps():
    """The "+ add new APN" icon lives on the APN *list* screen, not the
    edit *form* (these three dumps, at three scroll positions). It's now
    captured separately — see apn_restricted_SHG10.xml and the tests below
    — but these edit-form dumps genuinely never had it, confirming it
    wasn't an oversight to look for it here."""
    for xml in (APN_ENTRY_TOP_XML, APN_ENTRY_MIDDLE_XML, APN_ENTRY_BOTTOM_XML):
        # No node in any of these dumps is a bare "+"-style add affordance;
        # spot-check that the known overflow/up-nav content-descs are the
        # only icon-only controls present alongside the field rows.
        assert find_by_content_desc(xml, "追加") is None


# --- APN list screen, restricted-user variant (real, tests/fixtures/
# apn_restricted_SHG10.xml, 2026-09-11) — the actual screen
# android.settings.APN_SETTINGS lands on for this SIM/user, showing
# 「このユーザーはアクセスポイント名設定を利用できません」 and no existing
# entries, but with a fully real, working "+" button. -----------------------


def test_add_new_apn_button_has_real_unambiguous_content_desc():
    """Settles what apn_restricted_SHG10.xml's TODO left open: "+" DOES
    have its own stable identifier — content-desc "新しい APN" ("New
    APN") — it just isn't a resource-id. apn_setup.py now taps it directly
    via this content-desc instead of estimating a position from the
    adjacent overflow icon."""
    add_button = find_by_content_desc(APN_RESTRICTED_XML, "新しい APN")
    assert add_button is not None


def test_add_new_apn_button_sits_immediately_left_of_overflow_menu():
    """Confirms the layout assumption the (now-superseded) position-estimate
    fallback, tap_left_of_content_desc(), was built on: "+" and "⋮" are
    adjacent, same height, no gap. "+" bounds [837,83][969,215], "⋮" bounds
    [969,83][1080,215] — they share the x=969 edge exactly."""
    add_x, add_y = find_by_content_desc(APN_RESTRICTED_XML, "新しい APN")
    overflow_x, overflow_y = find_by_content_desc(APN_RESTRICTED_XML, "その他のオプション")
    assert add_y == overflow_y  # same vertical center
    assert add_x < overflow_x  # "+" is to the left


def test_restricted_screen_title_renders_via_content_desc_not_text():
    """The screen's "APN" title (com.android.settings:id/collapsing_toolbar)
    is a content-desc, exactly like "アクセスポイント名" on the
    SHARP-skinned screen — never a plain `text` node. An earlier version of
    _looks_like_apn_list_screen() checked find_by_text(ui_xml, "APN"),
    based on a screenshot read before this dump existed; that check would
    never have matched this real screen at all — there is no `text="APN"`
    node anywhere in this dump."""
    assert find_by_content_desc(APN_RESTRICTED_XML, "APN") is not None
    assert find_by_text(APN_RESTRICTED_XML, "APN") is None


def test_looks_like_apn_list_screen_recognizes_the_real_restricted_dump():
    """End-to-end confirmation that the fixed screen-recognition check
    accepts this exact real screen — the actual regression this fixture
    exists to catch."""
    assert _looks_like_apn_list_screen(APN_RESTRICTED_XML) is True


def test_restriction_warning_does_not_prevent_navigation_from_recognizing_the_screen():
    """The visible warning, 「このユーザーはアクセスポイント名設定を利用でき
    ません」, is present on this real dump but must not be mistaken for a
    hazardous/blocking condition by anything upstream — it's informational
    text on an otherwise fully functional screen (client-confirmed)."""
    assert (
        find_resource_id(APN_RESTRICTED_XML, "android:id/empty")
        is not None
    )
    assert _looks_like_apn_list_screen(APN_RESTRICTED_XML) is True
