"""Tests against real `uiautomator dump` XML captured from an actual SHG07
unit (serial 353681650397052, see docs/record.md) — as opposed to the
hand-written Stage A fixtures in test_ui_automator.py.

Unlike test_real_shg10_fixtures.py, these are the FIRST real captures for
this model — config/models/sharp_aquos_sense6s.yaml's values are inherited
from SHG10, not independently confirmed (see that file's header and
PENDING_REAL_DEVICE_DATA.md), so what these tests can actually pin down is
limited to what's been captured so far.
"""

from pathlib import Path

import pytest

from src.device.ui_automator import (
    AmbiguousResourceIdError,
    find_by_content_desc,
    find_resource_id,
    get_node_text,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "AQUOS sense6s（SHG07）"

APN_INPUT_DIALOG_XML = (FIXTURES_DIR / "apn_input_dialog_SHG07.xml").read_text(encoding="utf-8")
MOBILE_NETWORK_XML = (FIXTURES_DIR / "mobile_network_SHG07.xml").read_text(encoding="utf-8")


def test_apn_field_dialog_title_reads_apn():
    """Confirms which field's dialog this capture is — "APN" (the value
    field), not "名前" (the name field)."""
    assert get_node_text(APN_INPUT_DIALOG_XML, "com.android.settings:id/alertTitle") == "APN"


def test_apn_field_dialog_structure_matches_shg10_inherited_ids():
    """The dialog's ids (android:id/edit, android:id/button1/button2) are
    exactly what config/models/sharp_aquos_sense6s.yaml inherited from
    SHG10 — this dump confirms the *structure* carried over correctly for
    this field, independent of the separate IME/character-entry problem
    the client reported for the same screen (see
    docs/record.md — that's about what input_ascii_direct()/
    input_digits_direct() type INTO this dialog, not whether the dialog
    itself is reachable with the right ids)."""
    assert find_resource_id(APN_INPUT_DIALOG_XML, "android:id/edit") is not None
    assert get_node_text(APN_INPUT_DIALOG_XML, "android:id/button1") == "OK"
    assert get_node_text(APN_INPUT_DIALOG_XML, "android:id/button2") == "キャンセル"


# --- Mobile network (carrier-specific) settings screen, 2026-09-18 ---------
# Real finding: android.settings.APN_SETTINGS reaches a non-authoritative
# APN context — the real, live one is reached by navigating to THIS screen
# (Settings > Network & internet > SIM > Rakuten) and tapping its
# "アクセス ポイント名" row. See apn_setup.py's _navigate_apn_menu()
# docstring for the full account.


def test_mobile_network_screen_title_is_the_carrier_name():
    """The collapsing_toolbar's content-desc is the SIM's carrier name
    ("Rakuten"), not a generic "Mobile network" label — confirms this is
    the per-SIM settings screen, not a shared/generic one."""
    assert find_by_content_desc(MOBILE_NETWORK_XML, "Rakuten") is not None


def test_mobile_network_row_titles_share_generic_id():
    """Every row on this screen (モバイルデータ, ローミング, アクセス
    ポイント名, ...) shares the same generic android:id/title, same
    pattern as every other Settings screen captured so far — must fail
    loudly without a text= disambiguator."""
    with pytest.raises(AmbiguousResourceIdError):
        find_resource_id(MOBILE_NETWORK_XML, "android:id/title")


def test_access_point_names_row_is_real_and_tappable():
    """The critical real finding this fixture exists to pin down: "アクセス
    ポイント名" (WITH a space) is a genuine, tappable android:id/title row
    — distinct from "アクセスポイント名" (no space), the destination
    screen's own title, which is what caused this exact step to be
    mistakenly judged untappable and dropped from an earlier version of
    apn_setup.py's config."""
    coords = find_resource_id(MOBILE_NETWORK_XML, "android:id/title", text="アクセス ポイント名")
    assert coords is not None


def test_access_point_names_row_text_has_a_space_not_the_title_variant():
    """Guards against ever silently reverting to the wrong (no-space)
    string — searching for that variant among tappable rows must find
    nothing at all on this screen (it never appears here as a row's
    text, only the WITH-space variant does)."""
    assert find_resource_id(MOBILE_NETWORK_XML, "android:id/title", text="アクセスポイント名") is None
