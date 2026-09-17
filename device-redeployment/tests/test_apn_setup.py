"""Tests for src/phase2/apn_setup.py — both the legacy literal-resource-id
field shape (still used by the 3 models untouched by Stage B) and the new
label-based field shape (SHG10 — real field rows share one generic
resource-id, disambiguated by label text; see docs/record.md), plus the
android.settings.APN_SETTINGS intent navigation added after hand-testing
(2026-09-08/09) found the old menu_path's final step ("アクセスポイント名")
could never succeed: that text is the *destination screen's own title*,
rendered via content-desc on the toolbar (same pattern as the edit form's
"アクセスポイントの編集"), never a tappable `text` node — there was nothing
there to find, not a resource-id/text mismatch to work around."""

import logging
import xml.etree.ElementTree as ET

from src.device.model_profile import ModelProfile
from src.phase2.apn_setup import configure_apn
from tests.fakes import FakeAdbClient

# Reverse of ui_automator.py's input_digits_direct()/input_ascii_direct()
# keycode maps — used only by _EchoingEditFieldMixin below to reconstruct
# what a real device's EditText would actually show after typing.
_KEYEVENT_TO_CHAR = {
    **{f"KEYCODE_{d}": d for d in "0123456789"},
    **{f"KEYCODE_{c.upper()}": c for c in "abcdefghijklmnopqrstuvwxyz"},
    "KEYCODE_PERIOD": ".",
    "KEYCODE_MINUS": "-",
}


class _EchoingEditFieldMixin:
    """Mix into a FakeAdbClient subclass so that after input_text_direct()/
    input_ascii_direct()/input_digits_direct() "type" a value via shell(),
    the *next* dump reflects it on the `android:id/edit` node — modeling a
    real device's IME correctly committing what was typed. This is the
    happy-path counterpart to the 2026-09-15 read-back verification added
    to _fill_labeled_field() (real finding: SHG07's IME silently
    transformed typed text instead) — without this, every hand-written
    static fixture's edit node has no `text` at all, which the new check
    would now (correctly) treat as every field failing to commit.

    Resets whenever a new `input tap` happens (a new dialog's own typing
    session starting) — every profile fixture in this file uses
    "android:id/edit" for dialog_edit_field_resource_id, so that's hardcoded
    here rather than threaded through every call site.
    """

    _EDIT_FIELD_RESOURCE_ID = "android:id/edit"
    _typed = ""

    def shell(self, command, timeout=30):
        result = super().shell(command, timeout=timeout)
        if command.startswith("input tap"):
            self._typed = ""
        elif command.startswith('input text "'):
            self._typed = command[len('input text "') : -1]
        elif command.startswith("input keyevent "):
            keycode = command[len("input keyevent ") :]
            self._typed += _KEYEVENT_TO_CHAR.get(keycode, "")
        return result

    def pull(self, remote_path, local_path):
        result = super().pull(remote_path, local_path)
        if self._typed:
            with open(local_path, encoding="utf-8") as fh:
                xml_text = fh.read()
            if f'resource-id="{self._EDIT_FIELD_RESOURCE_ID}"' in xml_text:
                root = ET.fromstring(xml_text)
                for node in root.iter("node"):
                    if node.get("resource-id") == self._EDIT_FIELD_RESOURCE_ID:
                        node.set("text", self._typed)
                with open(local_path, "w", encoding="utf-8") as fh:
                    fh.write(ET.tostring(root, encoding="unicode"))
        return result


class EchoingFakeAdbClient(_EchoingEditFieldMixin, FakeAdbClient):
    """Plain FakeAdbClient + _EchoingEditFieldMixin, for tests that need
    correct field-typing echo but none of ApnPostSaveClient's/
    ScrollRevealsMncClient's other stateful behavior."""

LEGACY_PROFILE = ModelProfile(
    {
        "model": "Test Legacy",
        "model_number": "TST01",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            "menu_path": ["Settings", "Network"],
            "name_field_resource_id": "apn:name",
            "apn_field_resource_id": "apn:apn",
            "save_button_resource_id": "apn:save",
        },
    }
)

LEGACY_SCREEN_XML = """<hierarchy>
  <node text="Settings" bounds="[0,0][100,100]" />
  <node text="Network" bounds="[0,100][100,200]" />
  <node resource-id="apn:name" bounds="[0,200][100,300]" />
  <node resource-id="apn:apn" bounds="[0,300][100,400]" />
  <node resource-id="apn:save" bounds="[0,400][100,500]" />
</hierarchy>"""

# menu_path now ends at the gear icon (settings_button) — the real,
# hand-confirmed fallback path — not at "アクセスポイント名", which was never
# a valid tap target (see module docstring).
LABELED_PROFILE = ModelProfile(
    {
        "model": "SHG10-like Test",
        "model_number": "TST02",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            "menu_path": [
                {"type": "text", "value": "設定"},
                {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
            ],
            "field_row_resource_id": "android:id/title",
            "name_field_label": "名前",
            "apn_field_label": "APN",
            "mcc_field_label": "MCC",
            "mnc_field_label": "MNC",
            "dialog_edit_field_resource_id": "android:id/edit",
            "dialog_confirm_button_resource_id": "android:id/button1",
            "add_button_resource_id": None,
            "save_button_resource_id": None,
        },
    }
)

# The APN list screen as reached via the android.settings.APN_SETTINGS
# intent: content-desc carries the screen's own title (real pattern,
# confirmed by analogy with the edit form's "アクセスポイントの編集" — see
# tests/fixtures/apn_entry_*_SHG10.xml), so the intent-landing check
# succeeds immediately and no menu_path taps happen at all. Also includes
# every field row + the best-guess dialog ids, reused for every dump call
# throughout field-filling.
LABELED_SCREEN_XML = """<hierarchy>
  <node content-desc="アクセスポイント名" bounds="[0,0][1080,100]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
</hierarchy>"""

# Real bug (client screenshot, 2026-09-15, SHG07): typing "rakuten.jp"
# produced "らくてん。" in the field — the active IME's romaji-to-kana
# auto-conversion silently transformed it. Every step up to and including
# the typing call itself "succeeded" with no error from ui_automator's
# point of view; only reading back the field's actual committed text
# reveals the mismatch.
MISTRANSLATED_EDIT_FIELD_XML = LABELED_SCREEN_XML.replace(
    '<node resource-id="android:id/edit" bounds="[0,700][100,800]" />',
    '<node resource-id="android:id/edit" text="らくてん。" bounds="[0,700][100,800]" />',
)


def test_fill_labeled_field_fails_loudly_when_typed_text_is_transformed():
    """The actual real-world failure this project hit: nothing before the
    2026-09-15 read-back check could have caught this (the row tap, the
    edit-field tap, and the typing call itself all "succeed"). Must fail
    loud and — critically — never tap confirm on a field that doesn't
    actually contain what was typed, so a transformed value is never
    silently saved."""
    client = FakeAdbClient(ui_dumps=[MISTRANSLATED_EDIT_FIELD_XML] * 30)
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    assert result is False
    confirm_tap = "input tap {} {}".format((0 + 100) // 2, (800 + 900) // 2)
    assert confirm_tap not in client.shell_calls


# Real finding (2026-09-15): simply returning False on a mismatch left the
# dialog open — the *next* run's android.settings.APN_SETTINGS intent then
# failed to land on a recognizable screen on every attempt, including its
# very first, because the stuck dialog from the previous run's failure was
# still covering it. dialog_cancel_button_resource_id lets apn_setup.py
# back out cleanly instead.
CANCEL_BUTTON_PROFILE = ModelProfile(
    {
        "model": "SHG-like Cancel-Button Test",
        "model_number": "TST06",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {**LABELED_PROFILE.apn_settings(), "dialog_cancel_button_resource_id": "android:id/button2"},
    }
)

MISTRANSLATED_EDIT_FIELD_WITH_CANCEL_XML = MISTRANSLATED_EDIT_FIELD_XML.replace(
    '<node resource-id="android:id/button1" bounds="[0,800][100,900]" />',
    '<node resource-id="android:id/button2" bounds="[0,900][100,1000]" />\n'
    '  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />',
)


def test_fill_labeled_field_taps_cancel_to_back_out_of_mismatched_dialog():
    """When dialog_cancel_button_resource_id is configured, a mismatch must
    tap it to leave the device in a clean state — not just fail and leave
    the dialog open, which is what caused the real cascading navigation
    failure on the next run."""
    client = FakeAdbClient(ui_dumps=[MISTRANSLATED_EDIT_FIELD_WITH_CANCEL_XML] * 30)
    result = configure_apn(client, CANCEL_BUTTON_PROFILE, "rakuten.jp", "440", "11")
    assert result is False
    cancel_tap = "input tap {} {}".format((0 + 100) // 2, (900 + 1000) // 2)
    assert cancel_tap in client.shell_calls
    confirm_tap = "input tap {} {}".format((0 + 100) // 2, (800 + 900) // 2)
    assert confirm_tap not in client.shell_calls


# Real finding (2026-09-15, second cascading-failure round): cancelling the
# *field* dialog alone wasn't enough either — it leaves the device on the
# in-progress "new entry" edit *form*, not back on the APN *list*. The next
# run's APN_SETTINGS intent then landed on that leftover form instead of
# the list, still failing navigation. navigate_up_content_desc lets
# apn_setup.py fully exit the abandoned entry as a second cleanup layer.
NAVIGATE_UP_PROFILE = ModelProfile(
    {
        "model": "SHG-like Navigate-Up Test",
        "model_number": "TST07",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            **CANCEL_BUTTON_PROFILE.apn_settings(),
            "navigate_up_content_desc": "上へ移動",
        },
    }
)

MISTRANSLATED_EDIT_FIELD_WITH_NAVIGATE_UP_XML = MISTRANSLATED_EDIT_FIELD_WITH_CANCEL_XML.replace(
    "<hierarchy>",
    '<hierarchy>\n  <node content-desc="上へ移動" bounds="[0,72][154,226]" />',
)


def test_fill_labeled_field_taps_navigate_up_after_cancel_on_mismatch():
    """When navigate_up_content_desc is also configured, a mismatch must
    tap it too, after Cancel — fully exiting the abandoned new-entry form
    (not just closing the field's own dialog) so the device lands back on
    the APN list, not a leftover edit form, for the next run."""
    client = FakeAdbClient(ui_dumps=[MISTRANSLATED_EDIT_FIELD_WITH_NAVIGATE_UP_XML] * 30)
    result = configure_apn(client, NAVIGATE_UP_PROFILE, "rakuten.jp", "440", "11")
    assert result is False
    cancel_tap = "input tap {} {}".format((0 + 100) // 2, (900 + 1000) // 2)
    assert cancel_tap in client.shell_calls
    navigate_up_tap = "input tap {} {}".format((0 + 154) // 2, (72 + 226) // 2)
    assert navigate_up_tap in client.shell_calls
    confirm_tap = "input tap {} {}".format((0 + 100) // 2, (800 + 900) // 2)
    assert confirm_tap not in client.shell_calls


def test_configure_apn_legacy_shape_succeeds():
    client = FakeAdbClient(ui_dumps=[LEGACY_SCREEN_XML] * 10)
    result = configure_apn(client, LEGACY_PROFILE, "internet", "310", "260")
    assert result is True


def test_configure_apn_labeled_shape_fills_name_apn_mcc_mnc():
    client = FakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    # save_button_resource_id is None (unresolved, per docs/record.md) —
    # configure_apn() must fail loudly rather than pretend it saved.
    assert result is False


def test_configure_apn_labeled_shape_injects_correct_values_before_failing_at_save():
    """名前/APN go through input_text_direct() (`input text`), not
    inject_text() (ADB Keyboard broadcast) — confirmed necessary on real
    hardware (docs/record.md, 2026-09-08): a real run showed inject_text()'s
    broadcast does nothing at all on this device (a Wi-Fi password field
    stayed empty despite no errors). MCC/MNC go through input_digits_direct()
    (per-digit keyevents) instead of input_text_direct() — a *later* real
    finding (2026-09-11) showed `input text` commits full-width digits on
    this device; see _fill_labeled_field()'s docstring."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    direct_injected = [c for c in client.shell_calls if c.startswith("input text ")]
    assert not any("ADB_INPUT_TEXT" in c for c in client.shell_calls)
    assert 'input text "rakuten.jp"' in direct_injected
    # 440 -> KEYCODE_4, KEYCODE_4, KEYCODE_0; never as `input text "440"`.
    assert "input keyevent KEYCODE_4" in client.shell_calls
    assert "input keyevent KEYCODE_0" in client.shell_calls
    assert 'input text "440"' not in client.shell_calls
    # 11 -> KEYCODE_1, KEYCODE_1 (nothing else in this test types a "1").
    assert client.shell_calls.count("input keyevent KEYCODE_1") == 2
    assert 'input text "11"' not in client.shell_calls


# SHG07 (2026-09-14): unlike SHG10, plain `input text` alphanumeric entry
# is affected by the active IME there too, not just MCC/MNC — client
# report + tests/fixtures/apn_input_dialog_SHG07.xml. Opt-in per model via
# apn_settings.use_keyevent_text_entry, since SHG10 already proved
# input_text_direct() works fine for it there (real end-to-end success,
# 2026-09-11) and this must not change SHG10's already-working behavior.
KEYEVENT_TEXT_ENTRY_PROFILE = ModelProfile(
    {
        "model": "SHG07-like Test",
        "model_number": "TST05",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {**LABELED_PROFILE.apn_settings(), "use_keyevent_text_entry": True},
    }
)


def test_configure_apn_uses_keyevents_for_all_fields_when_flagged():
    """With use_keyevent_text_entry=True, 名前/APN go through
    input_ascii_direct() (per-character keyevents) instead of
    input_text_direct() — MCC/MNC already did via numeric_only regardless
    of this flag, so this only changes the two text fields."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, KEYEVENT_TEXT_ENTRY_PROFILE, "rakuten.jp", "440", "11")
    assert not any(c.startswith("input text ") for c in client.shell_calls)
    # "rakuten.jp" typed via keyevents: r-a-k-u-t-e-n-.-j-p
    for letter in "rakutenjp":
        assert f"input keyevent KEYCODE_{letter.upper()}" in client.shell_calls
    assert "input keyevent KEYCODE_PERIOD" in client.shell_calls


def test_configure_apn_labeled_shape_still_uses_input_text_by_default():
    """Confirms the flag is opt-in, not a global behavior change — SHG10's
    profile (LABELED_PROFILE here has no use_keyevent_text_entry key) must
    keep using input_text_direct() for 名前/APN exactly as before."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    assert 'input text "rakuten.jp"' in client.shell_calls


# SHG07 (2026-09-15): the on-screen keyboard's かな/英数 mode-toggle key,
# found via Android's own Pointer Location developer tool and confirmed
# working via `adb shell input tap` (not just manual touch) — see
# tap_at_coordinates()'s docstring for why no resource-id is possible here.
KEYBOARD_TOGGLE_PROFILE = ModelProfile(
    {
        "model": "SHG07-like Keyboard-Toggle Test",
        "model_number": "TST08",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {**LABELED_PROFILE.apn_settings(), "keyboard_mode_toggle_tap": [106, 2239]},
    }
)


def test_configure_apn_taps_keyboard_toggle_twice_before_every_field():
    """Must tap the confirmed coordinate exactly twice (the confirmed
    real-hardware recipe — see docs/record.md, 2026-09-15) before typing
    into EVERY field, including MCC/MNC — a live run the same day showed
    input_digits_direct() also gets digits converted to full-width
    ("440" -> "４４０") when the keyboard is left in kana mode; the
    earlier assumption that digit keyevents are universally immune only
    held on SHG10, not SHG07."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    toggle_tap = "input tap 106 2239"
    # 4 fields (名前, APN, MCC, MNC) x 2 taps each = 8 total.
    assert client.shell_calls.count(toggle_tap) == 8


def test_configure_apn_keyboard_toggle_tap_is_opt_in():
    """Confirms this is model-specific, not applied everywhere — SHG10's
    profile (LABELED_PROFILE here has no keyboard_mode_toggle_tap key)
    must never tap this SHG07-specific coordinate."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    assert "input tap 106 2239" not in client.shell_calls


# SOG07 (2026-09-17): a real run showed the SAME toggle coordinate used for
# 名前/APN does NOT work for MCC/MNC on Sony hardware — a screenshot
# confirmed those fields open a genuinely different numeric-only keypad
# whose own toggle key sits at a different X. keyboard_mode_toggle_tap_numeric
# is this keypad's own, independently-confirmed coordinate.
NUMERIC_KEYBOARD_TOGGLE_PROFILE = ModelProfile(
    {
        "model": "SOG07-like Numeric-Keyboard-Toggle Test",
        "model_number": "TST09",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            **LABELED_PROFILE.apn_settings(),
            "keyboard_mode_toggle_tap": [145, 2308],
            "keyboard_mode_toggle_tap_numeric": [93, 2300],
        },
    }
)


def test_configure_apn_uses_numeric_toggle_coordinate_for_mcc_mnc_only():
    """名前/APN must tap the text-keyboard coordinate; MCC/MNC must tap the
    separate numeric-keypad coordinate instead — not the text one."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, NUMERIC_KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    text_tap = "input tap 145 2308"
    numeric_tap = "input tap 93 2300"
    # 名前, APN = 2 fields x 2 taps = 4 on the text coordinate.
    assert client.shell_calls.count(text_tap) == 4
    # MCC, MNC = 2 fields x 2 taps = 4 on the numeric coordinate.
    assert client.shell_calls.count(numeric_tap) == 4


def test_configure_apn_numeric_toggle_falls_back_to_shared_coordinate_when_unset():
    """SHG07's profile only sets keyboard_mode_toggle_tap (no separate
    numeric variant) — MCC/MNC must keep using that same coordinate,
    unchanged from before this feature existed."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    toggle_tap = "input tap 106 2239"
    assert client.shell_calls.count(toggle_tap) == 8


def test_configure_apn_missing_save_button_never_taps_anything_claiming_save():
    """With save_button_resource_id unresolved (None), configure_apn() must
    not silently guess a save action — this is the direct instruction from
    docs/record.md Task 2: leave marked TODO rather than guess."""
    client = FakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    assert result is False


def test_configure_apn_fails_loudly_when_menu_navigation_fails():
    client = FakeAdbClient(ui_dumps=["<hierarchy></hierarchy>"])
    result = configure_apn(client, LEGACY_PROFILE, "internet", "310", "260")
    assert result is False


# --- Per-field dialog confirm-button hardening (2026-09-11): a real run
# reported values typed correctly up through MNC but the entry never
# actually saved — root cause was the OLD behavior here (soft-warn and
# continue when the best-guess dialog_confirm_button_resource_id isn't
# found), which leaves the dialog stuck open and lets every later tap
# (next field, overflow menu, save) land on/be swallowed by it instead of
# its real target. Both taps are hard failures now. -------------------------

NO_CONFIRM_BUTTON_SCREEN_XML = """<hierarchy>
  <node content-desc="アクセスポイント名" bounds="[0,0][1080,100]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
</hierarchy>"""

NO_EDIT_FIELD_SCREEN_XML = """<hierarchy>
  <node content-desc="アクセスポイント名" bounds="[0,0][1080,100]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
</hierarchy>"""


def test_configure_apn_fails_loudly_when_dialog_confirm_button_not_found():
    """If the best-guess dialog_confirm_button_resource_id ("android:id/
    button1") isn't found after typing, this must be a HARD failure, not a
    warning-and-continue — the typed value was never actually committed,
    and continuing would mean every later tap targets the wrong (still
    covered by a stuck dialog) screen."""
    client = FakeAdbClient(ui_dumps=[NO_CONFIRM_BUTTON_SCREEN_XML] * 30)
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    assert result is False
    # Must fail on the very first field (名前) — never even reach APN/MCC/MNC.
    typed = [c for c in client.shell_calls if c.startswith("input text ")]
    assert typed == ['input text "rakuten.jp"']


def test_configure_apn_fails_loudly_when_dialog_edit_field_not_found():
    """Same hardening for the edit-field tap: refuse to type blindly into
    whatever currently has focus if the best-guess id isn't found."""
    client = FakeAdbClient(ui_dumps=[NO_EDIT_FIELD_SCREEN_XML] * 30)
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    assert result is False
    # Must fail before ever typing anything.
    assert not any(c.startswith("input text ") for c in client.shell_calls)


# --- APN_SETTINGS intent navigation (real hand-testing, 2026-09-08/09) -----


def test_configure_apn_reaches_list_via_intent_with_no_menu_path_taps():
    """When android.settings.APN_SETTINGS lands on a screen whose
    content-desc confirms "アクセスポイント名" (the real screen-title
    pattern), no menu_path step should be tapped at all — not even the
    first one."""
    client = FakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    assert any(c == "am start -a android.settings.APN_SETTINGS" for c in client.shell_calls)
    settings_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    assert settings_tap not in client.shell_calls


def test_configure_apn_recognizes_content_desc_apn_title_variant():
    """Real dump (tests/fixtures/apn_restricted_SHG10.xml, 2026-09-11): the
    screen reached via the android.settings.APN_SETTINGS intent on this
    device shows its "APN" title via `content-desc` on the toolbar
    (`com.android.settings:id/collapsing_toolbar`), not the content-desc
    "アクセスポイント名" title used by the SHARP-skinned screen reached via
    manual navigation, and — critically — never as a plain `text` node
    (an earlier version of this test used `text="APN"`, based on a
    screenshot read before this real dump existed; that fixture wouldn't
    match anything on the actual device). Both content-desc variants must
    be recognized as "arrived" — no menu_path taps for either."""
    content_desc_title_screen = """<hierarchy>
  <node resource-id="com.android.settings:id/collapsing_toolbar" content-desc="APN" bounds="[0,0][1080,100]" />
  <node resource-id="android:id/empty" text="このユーザーはアクセスポイント名設定を利用できません" bounds="[0,100][1080,200]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
</hierarchy>"""
    client = FakeAdbClient(ui_dumps=[content_desc_title_screen] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    assert any(c == "am start -a android.settings.APN_SETTINGS" for c in client.shell_calls)
    # Positive proof navigation was recognized (not just coincidentally
    # unreachable another way): field-filling proceeded far enough to tap
    # the 名前 row, which only happens once _navigate_apn_menu() returns
    # True — menu_path's steps (which this fixture has nothing matching)
    # were never needed.
    name_field_tap = "input tap {} {}".format((0 + 100) // 2, (300 + 400) // 2)
    assert name_field_tap in client.shell_calls


def test_configure_apn_falls_back_to_menu_path_when_intent_command_fails():
    class NoIntentClient(FakeAdbClient):
        def shell(self, command, timeout=30):
            if command == "am start -a android.settings.APN_SETTINGS":
                from src.device.adb_client import AdbCommandError
                raise AdbCommandError(command, "intent not supported on this build")
            return super().shell(command, timeout=timeout)

    # This screen has no content-desc title (as if the intent never ran) but
    # does have the full menu_path's targets: "設定" text, then the gear
    # icon.
    menu_path_screen = """<hierarchy>
  <node text="設定" bounds="[0,0][100,100]" />
  <node resource-id="com.android.settings:id/settings_button" bounds="[0,100][100,200]" />
  <node content-desc="アクセスポイント名" bounds="[0,200][1080,300]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
</hierarchy>"""
    client = NoIntentClient(ui_dumps=[menu_path_screen] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    settings_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    gear_tap = "input tap {} {}".format((0 + 100) // 2, (100 + 200) // 2)
    assert settings_tap in client.shell_calls
    assert gear_tap in client.shell_calls


def test_configure_apn_falls_back_to_menu_path_when_intent_lands_elsewhere():
    """Intent command runs without error, but the resulting screen doesn't
    carry the APN list's content-desc title — must fall back to menu_path
    rather than assume the intent worked."""
    home_screen_xml = '<hierarchy><node text="Home" bounds="[0,0][10,10]" /></hierarchy>'
    menu_path_screen = """<hierarchy>
  <node text="設定" bounds="[0,0][100,100]" />
  <node resource-id="com.android.settings:id/settings_button" bounds="[0,100][100,200]" />
  <node content-desc="アクセスポイント名" bounds="[0,200][1080,300]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
</hierarchy>"""
    client = FakeAdbClient(ui_dumps=[home_screen_xml] + [menu_path_screen] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    settings_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    gear_tap = "input tap {} {}".format((0 + 100) // 2, (100 + 200) // 2)
    assert settings_tap in client.shell_calls
    assert gear_tap in client.shell_calls


def test_configure_apn_labeled_shape_missing_mcc_label_fails_cleanly():
    """MCC/MNC are mandatory for the labeled shape (confirmed on real
    hardware, 2026-09-08) — a profile missing mcc_field_label must fail
    loudly, not silently skip the field."""
    profile = ModelProfile(
        {
            "model": "Incomplete Labeled",
            "model_number": "TST04",
            "manufacturer": "Test",
            "android_version": 14,
            "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
            "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
            "apn_settings": {
                "menu_path": ["Settings"],
                "field_row_resource_id": "android:id/title",
                "name_field_label": "名前",
                "apn_field_label": "APN",
                # mcc_field_label / mnc_field_label deliberately missing
            },
        }
    )
    client = FakeAdbClient(
        ui_dumps=["<hierarchy><node text=\"Settings\" bounds=\"[0,0][10,10]\"/></hierarchy>"]
    )
    result = configure_apn(client, profile, "internet", "440", "11")
    assert result is False


def test_configure_apn_rejects_malformed_mcc_before_touching_device():
    client = FakeAdbClient(ui_dumps=["<hierarchy></hierarchy>"])
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "44", "11")
    assert result is False
    assert client.shell_calls == []


def test_configure_apn_rejects_malformed_mnc_before_touching_device():
    client = FakeAdbClient(ui_dumps=["<hierarchy></hierarchy>"])
    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "1")
    assert result is False
    assert client.shell_calls == []


def test_mcc_mnc_length_patterns():
    """MCC exactly 3 digits, MNC 2 or 3 — the device's own validation
    messages, verbatim (docs/record.md, 2026-09-08):
    'MCC欄は3桁で指定してください。' / 'MNC欄は2桁か3桁で指定してください。'"""
    from src.phase2.apn_setup import _MCC_PATTERN, _MNC_PATTERN

    assert _MCC_PATTERN.fullmatch("440")
    assert not _MCC_PATTERN.fullmatch("44")
    assert not _MCC_PATTERN.fullmatch("4400")
    assert _MNC_PATTERN.fullmatch("11")
    assert _MNC_PATTERN.fullmatch("110")
    assert not _MNC_PATTERN.fullmatch("1")


# --- Scroll-to-reveal for below-the-fold fields (real hardware, 2026-09-08:
# MCC/MNC rows are below the fold in the scrollable form) ------------------


class ScrollRevealsMncClient(_EchoingEditFieldMixin, FakeAdbClient):
    """The MNC row is stripped out of every dump until at least one scroll
    (`input swipe`) has happened, then present afterward — models the real
    finding (2026-09-08): MCC/MNC rows are below the fold in the
    scrollable form and genuinely absent from the dump until scrolled into
    view, not just "hard to find" in an already-complete dump."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scrolled = False

    def shell(self, command, timeout=30):
        if command.startswith("input swipe"):
            self._scrolled = True
        return super().shell(command, timeout=timeout)

    def _next_ui_dump(self):
        xml = super()._next_ui_dump()
        if not self._scrolled:
            xml = xml.replace(
                '<node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />',
                "",
            )
        return xml


def test_fill_labeled_field_scrolls_when_row_not_immediately_present():
    client = ScrollRevealsMncClient(ui_dumps=[LABELED_SCREEN_XML] * 30)

    configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert any(c.startswith("input swipe") for c in client.shell_calls)
    # MNC "11" goes through input_digits_direct() (keyevents), not
    # `input text` — see test_configure_apn_labeled_shape_injects_correct_
    # values_before_failing_at_save.
    assert client.shell_calls.count("input keyevent KEYCODE_1") == 2


# --- Real save flow (SHG10, confirmed 2026-09-08): overflow menu -> "保存",
# blocked by a validation dialog if any required field was empty/invalid ---


class ApnPostSaveClient(_EchoingEditFieldMixin, FakeAdbClient):
    """After the "保存" tap (bounds hardcoded to match SAVE_FLOW_SCREEN_XML
    below), subsequent uiautomator dumps return `post_save_xml` instead of
    whatever the base ui_dumps list would serve next — models the real
    screen transition after tapping Save without needing to hand-count
    exact dump_ui() call positions through nav + 4 fields + the menu."""

    SAVE_TAP = "input tap 50 950"

    def __init__(self, *, post_save_xml: str, **kwargs):
        super().__init__(**kwargs)
        self.post_save_xml = post_save_xml
        self._save_tapped = False

    def shell(self, command, timeout=30):
        result = super().shell(command, timeout=timeout)
        if command == self.SAVE_TAP:
            self._save_tapped = True
        return result

    def pull(self, remote_path, local_path):
        if self._save_tapped:
            with open(local_path, "w", encoding="utf-8") as fh:
                fh.write(self.post_save_xml)
            self.pulled_files[remote_path] = local_path
            return self.pull_result
        return super().pull(remote_path, local_path)


SAVE_FLOW_PROFILE = ModelProfile(
    {
        "model": "SHG10-like Save Test",
        "model_number": "TST03",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            "menu_path": [
                {"type": "text", "value": "設定"},
                {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
            ],
            "field_row_resource_id": "android:id/title",
            "name_field_label": "名前",
            "apn_field_label": "APN",
            "mcc_field_label": "MCC",
            "mnc_field_label": "MNC",
            "dialog_edit_field_resource_id": "android:id/edit",
            "dialog_confirm_button_resource_id": "android:id/button1",
            "add_button_resource_id": None,
            "overflow_menu_content_desc": "その他のオプション",
            # save_menu_item_text left unset — defaults to "保存"
        },
    }
)

SAVE_FLOW_SCREEN_XML = """<hierarchy>
  <node content-desc="アクセスポイント名" bounds="[0,0][1080,100]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
  <node content-desc="その他のオプション" bounds="[900,100][1000,200]" />
  <node resource-id="android:id/title" text="保存" bounds="[0,900][100,1000]" />
  <node resource-id="android:id/title" text="キャンセル" bounds="[0,1000][100,1100]" />
</hierarchy>"""

POST_SAVE_SUCCESS_XML = """<hierarchy>
  <node content-desc="アクセスポイント名" bounds="[0,0][1080,100]" />
  <node resource-id="android:id/title" text="rakuten.jp" bounds="[0,300][100,400]" />
</hierarchy>"""

POST_SAVE_VALIDATION_XML = """<hierarchy>
  <node text="MCC欄は3桁で指定してください。" resource-id="android:id/message" bounds="[0,0][100,100]" />
  <node text="OK" resource-id="android:id/button1" bounds="[500,500][600,600]" />
</hierarchy>"""

# The list not yet reflecting the new entry — no validation message either,
# just genuinely stale/not-yet-refreshed. See ApnPostSaveDelayedVisibilityClient.
POST_SAVE_NOT_YET_REFRESHED_XML = """<hierarchy>
  <node content-desc="アクセスポイント名" bounds="[0,0][1080,100]" />
</hierarchy>"""


def test_configure_apn_real_save_flow_succeeds_when_no_validation_dialog_appears():
    client = ApnPostSaveClient(
        ui_dumps=[SAVE_FLOW_SCREEN_XML] * 30, post_save_xml=POST_SAVE_SUCCESS_XML
    )
    result = configure_apn(client, SAVE_FLOW_PROFILE, "rakuten.jp", "440", "11")
    assert result is True
    assert ApnPostSaveClient.SAVE_TAP in client.shell_calls
    overflow_tap = "input tap {} {}".format((900 + 1000) // 2, (100 + 200) // 2)
    assert overflow_tap in client.shell_calls


class ApnPostSaveDelayedVisibilityClient(ApnPostSaveClient):
    """Real-hardware finding (2026-09-11): the APN list can take a moment
    to actually refresh after 保存 — the dump taken immediately after the
    tap can still show the pre-save state even though the save genuinely
    succeeded (confirmed by the client manually re-opening the screen
    moments later). Models that: the first post-save dump serves
    `post_save_xml` (not-yet-refreshed); every dump after that serves
    `delayed_post_save_xml` (refreshed, entry visible)."""

    def __init__(self, *, delayed_post_save_xml: str, **kwargs):
        super().__init__(**kwargs)
        self.delayed_post_save_xml = delayed_post_save_xml
        self._post_save_pull_count = 0

    def pull(self, remote_path, local_path):
        if self._save_tapped:
            self._post_save_pull_count += 1
            xml = self.post_save_xml if self._post_save_pull_count == 1 else self.delayed_post_save_xml
            with open(local_path, "w", encoding="utf-8") as fh:
                fh.write(xml)
            self.pulled_files[remote_path] = local_path
            return self.pull_result
        # super().pull() — not FakeAdbClient.pull() directly — so the MRO
        # still reaches _EchoingEditFieldMixin.pull() (via ApnPostSaveClient)
        # while not-yet-save-tapped, letting field-typing echo correctly.
        return super().pull(remote_path, local_path)


def test_configure_apn_retries_post_save_check_before_warning(monkeypatch, caplog):
    """The soft post-save visibility check retries once (after a short
    delay) before logging its "wasn't spotted" warning — real hardware
    showed the very first dump after 保存 can still show the pre-save
    state for a save that actually succeeded (2026-09-11). Must still
    return True either way (soft check, never a hard failure) — this test
    specifically confirms the retry finds it and no misleading warning
    fires."""
    monkeypatch.setattr("src.phase2.apn_setup.time.sleep", lambda _seconds: None)
    client = ApnPostSaveDelayedVisibilityClient(
        ui_dumps=[SAVE_FLOW_SCREEN_XML] * 30,
        post_save_xml=POST_SAVE_NOT_YET_REFRESHED_XML,
        delayed_post_save_xml=POST_SAVE_SUCCESS_XML,
    )

    with caplog.at_level(logging.INFO, logger="src.phase2.apn_setup"):
        result = configure_apn(client, SAVE_FLOW_PROFILE, "rakuten.jp", "440", "11")

    assert result is True
    messages = [r.getMessage() for r in caplog.records]
    assert not any("wasn't spotted" in m for m in messages)
    assert any("confirmed visible" in m for m in messages)


class ApnPostSaveRequiresRenavigationClient(ApnPostSaveClient):
    """Real-hardware finding (2026-09-15, SHG07): sometimes even the delay
    + re-dump of the SAME still-open list screen isn't enough — the client
    confirmed manually that simply waiting doesn't refresh it, but leaving
    and re-entering Settings does. Models that: every post-save dump on
    the same screen keeps serving the stale `post_save_xml`; only a fresh
    `android.settings.APN_SETTINGS` intent issued AFTER save switches to
    the refreshed `delayed_post_save_xml`."""

    def __init__(self, *, delayed_post_save_xml: str, **kwargs):
        super().__init__(**kwargs)
        self.delayed_post_save_xml = delayed_post_save_xml
        self._renavigated_after_save = False

    def shell(self, command, timeout=30):
        result = super().shell(command, timeout=timeout)
        if self._save_tapped and command == "am start -a android.settings.APN_SETTINGS":
            self._renavigated_after_save = True
        return result

    def pull(self, remote_path, local_path):
        if self._save_tapped:
            xml = self.delayed_post_save_xml if self._renavigated_after_save else self.post_save_xml
            with open(local_path, "w", encoding="utf-8") as fh:
                fh.write(xml)
            self.pulled_files[remote_path] = local_path
            return self.pull_result
        return super().pull(remote_path, local_path)


def test_configure_apn_falls_back_to_renavigation_when_waiting_alone_is_not_enough(
    monkeypatch, caplog
):
    """When even the delay+re-dump retry still doesn't find the entry, a
    fresh APN_SETTINGS intent must be tried before giving up — real
    hardware (2026-09-15, SHG07) showed waiting on the same already-open
    screen sometimes isn't enough, but a full re-navigation is. Still a
    soft check either way — must return True and log "confirmed visible",
    not the "wasn't spotted" warning."""
    monkeypatch.setattr("src.phase2.apn_setup.time.sleep", lambda _seconds: None)
    client = ApnPostSaveRequiresRenavigationClient(
        ui_dumps=[SAVE_FLOW_SCREEN_XML] * 30,
        post_save_xml=POST_SAVE_NOT_YET_REFRESHED_XML,
        delayed_post_save_xml=POST_SAVE_SUCCESS_XML,
    )

    with caplog.at_level(logging.INFO, logger="src.phase2.apn_setup"):
        result = configure_apn(client, SAVE_FLOW_PROFILE, "rakuten.jp", "440", "11")

    assert result is True
    messages = [r.getMessage() for r in caplog.records]
    assert not any("wasn't spotted" in m for m in messages)
    assert any("confirmed visible" in m for m in messages)


def test_configure_apn_taps_estimated_add_button_position_when_unresolved():
    """Real screenshot (2026-09-11): add_button_resource_id ("+") has never
    been captured (no dump of the list screen with an empty/known-count APN
    set exists) — but the "その他のオプション" ("⋮") overflow icon
    immediately to its right IS confirmed real, so configure_apn() must fall
    back to tap_left_of_content_desc() instead of silently skipping the tap
    (see PENDING_REAL_DEVICE_DATA.md)."""
    client = ApnPostSaveClient(
        ui_dumps=[SAVE_FLOW_SCREEN_XML] * 30, post_save_xml=POST_SAVE_SUCCESS_XML
    )
    result = configure_apn(client, SAVE_FLOW_PROFILE, "rakuten.jp", "440", "11")
    assert result is True
    # overflow icon bounds [900,100][1000,200] -> width 100 -> estimated "+"
    # tap at (900 - 100//2, (100+200)//2) = (850, 150).
    add_button_tap = "input tap 850 150"
    assert add_button_tap in client.shell_calls
    # It must happen before the fields are filled (add-new comes first).
    name_field_tap_index = client.shell_calls.index(
        "input tap {} {}".format((0 + 100) // 2, (300 + 400) // 2)
    )
    assert client.shell_calls.index(add_button_tap) < name_field_tap_index


# add_button_content_desc: the "+" button's own content-desc, now resolved
# on real hardware (tests/fixtures/apn_restricted_SHG10.xml, 2026-09-11:
# "新しい APN"). Takes priority over both add_button_resource_id (still
# unresolved) and the tap_left_of_content_desc() position estimate.
ADD_BUTTON_CONTENT_DESC_PROFILE = ModelProfile(
    {
        "model": "SHG10-like Add-Button Test",
        "model_number": "TST04",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            **SAVE_FLOW_PROFILE.apn_settings(),
            "add_button_content_desc": "新しい APN",
        },
    }
)

ADD_BUTTON_CONTENT_DESC_SCREEN_XML = SAVE_FLOW_SCREEN_XML.replace(
    '<node content-desc="その他のオプション" bounds="[900,100][1000,200]" />',
    '<node content-desc="新しい APN" bounds="[750,100][900,200]" />\n'
    '  <node content-desc="その他のオプション" bounds="[900,100][1000,200]" />',
)


def test_configure_apn_taps_real_add_button_content_desc_when_resolved():
    """Once add_button_content_desc is set, configure_apn() must tap it
    directly (tap_by_content_desc) instead of falling back to the
    positional estimate — the estimate exists only for models/screens
    where no real identifier for "+" has been captured at all."""
    client = ApnPostSaveClient(
        ui_dumps=[ADD_BUTTON_CONTENT_DESC_SCREEN_XML] * 30, post_save_xml=POST_SAVE_SUCCESS_XML
    )
    result = configure_apn(client, ADD_BUTTON_CONTENT_DESC_PROFILE, "rakuten.jp", "440", "11")
    assert result is True
    add_button_tap = "input tap {} {}".format((750 + 900) // 2, (100 + 200) // 2)
    assert add_button_tap in client.shell_calls
    # Must NOT fall back to the estimate (which would tap left of the
    # overflow icon at [900,100][1000,200] -> (850, 150) — a different,
    # wrong-for-this-case coordinate now that the real value is known).
    estimate_tap = "input tap 850 150"
    assert estimate_tap not in client.shell_calls


def test_configure_apn_real_save_flow_fails_loudly_on_validation_dialog():
    client = ApnPostSaveClient(
        ui_dumps=[SAVE_FLOW_SCREEN_XML] * 30, post_save_xml=POST_SAVE_VALIDATION_XML
    )
    result = configure_apn(client, SAVE_FLOW_PROFILE, "rakuten.jp", "440", "11")
    assert result is False
    assert ApnPostSaveClient.SAVE_TAP in client.shell_calls
    # Must NOT tap OK on the validation dialog — fail loud, don't retry blindly.
    ok_tap = "input tap {} {}".format((500 + 600) // 2, (500 + 600) // 2)
    assert ok_tap not in client.shell_calls


def test_configure_apn_legacy_missing_required_field_fails_cleanly():
    incomplete_profile = ModelProfile(
        {
            "model": "Broken",
            "model_number": "BRK",
            "manufacturer": "Test",
            "android_version": 13,
            "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
            "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
            "apn_settings": {"menu_path": ["Settings"]},  # nothing else
        }
    )
    client = FakeAdbClient(ui_dumps=["<hierarchy><node text=\"Settings\" bounds=\"[0,0][10,10]\"/></hierarchy>"])
    result = configure_apn(client, incomplete_profile, "internet", "310", "260")
    assert result is False
