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

from src.device.ui_automator import find_resource_id, get_node_text

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "AQUOS sense6s（SHG07）"

APN_INPUT_DIALOG_XML = (FIXTURES_DIR / "apn_input_dialog_SHG07.xml").read_text(encoding="utf-8")


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
