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

import pytest

from src.device.model_profile import ModelProfile
from src.phase2.apn_setup import _fill_labeled_field, configure_apn
from tests.fakes import FakeAdbClient


@pytest.fixture(autouse=True)
def _no_real_delays(monkeypatch):
    """_KEYBOARD_TOGGLE_TAP_DELAY_SECONDS (2026-09-17) and
    _POST_SAVE_RECHECK_DELAY_SECONDS both add a real time.sleep() in
    production code — stub it out for every test in this file so the
    suite stays fast; none of these tests assert on real elapsed time,
    only on call sequences/counts."""
    monkeypatch.setattr("src.phase2.apn_setup.time.sleep", lambda _seconds: None)

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

    `input text` APPENDS at the current cursor position (it synthesizes
    real keystrokes — a real device never clears the field first), so two
    separate `input text` calls for the same field must accumulate, not
    replace each other. This matters since 2026-09-17's probe-then-rest
    optimization for numeric fields calls it twice per field (a
    single-character probe, then the rest of the value) when
    use_text_entry_for_numeric is set.
    """

    _EDIT_FIELD_RESOURCE_ID = "android:id/edit"
    _typed = ""

    def shell(self, command, timeout=30):
        result = super().shell(command, timeout=timeout)
        if command.startswith("input tap"):
            self._typed = ""
        elif command.startswith('input text "'):
            self._typed += command[len('input text "') : -1]
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


class _CyclingKeyboardModeClient(FakeAdbClient):
    """Real root cause the client diagnosed on SOG07 (2026-09-17): the
    on-screen keyboard's mode-toggle key does NOT reset to a known state
    for each new field's dialog — it carries over from wherever the
    PREVIOUS field's typing left it. _EchoingEditFieldMixin's happy-path
    model (every typed value always echoes back correctly) can't exercise
    this; this client models a toggle key that advances through a
    fixed-length cycle on every tap of `toggle_coords` specifically, and
    PERSISTS that state across separate field dialogs. Typing while not in
    `_CORRECT_MODE` commits a fixed garbled marker instead of the real
    value, so a test can assert the retry-and-recheck logic in
    _fill_labeled_field() actually detects and corrects it — not just
    that taps happen."""

    _CORRECT_MODE = 0

    def __init__(self, *args, toggle_coords, cycle_length, starting_mode, **kwargs):
        super().__init__(*args, **kwargs)
        self._toggle_tap = f"input tap {toggle_coords[0]} {toggle_coords[1]}"
        self._cycle_length = cycle_length
        self._mode = starting_mode
        self._typed = ""

    def shell(self, command, timeout=30):
        result = super().shell(command, timeout=timeout)
        if command == self._toggle_tap:
            self._mode = (self._mode + 1) % self._cycle_length
        elif command.startswith("input tap"):
            # Any OTHER tap (the field row, the edit-field itself) is a
            # new dialog's own typing session starting — clears whatever
            # was typed, but deliberately does NOT touch self._mode: the
            # whole point being modeled here is that the toggle's mode
            # survives across these.
            self._typed = ""
        elif command.startswith('input text "'):
            # Appends, same real-device reasoning as
            # _EchoingEditFieldMixin's docstring above. When wrong, models
            # exactly one garbled character per `input text` CALL (not
            # per character of its content) — consistent with the
            # per-keyevent path below (one "ガ" per keystroke) now that
            # 2026-09-17's probe optimization means this can be called
            # with anywhere from one character to the whole value.
            value = command[len('input text "') : -1]
            self._typed += value if self._mode == self._CORRECT_MODE else "ガ"
        elif command == "input keyevent KEYCODE_DEL":
            self._typed = self._typed[:-1]
        elif command.startswith("input keyevent "):
            keycode = command[len("input keyevent ") :]
            if self._mode == self._CORRECT_MODE:
                self._typed += _KEYEVENT_TO_CHAR.get(keycode, "")
            else:
                self._typed += "ガ"
        return result

    def pull(self, remote_path, local_path):
        result = super().pull(remote_path, local_path)
        with open(local_path, encoding="utf-8") as fh:
            xml_text = fh.read()
        if 'resource-id="android:id/edit"' in xml_text:
            root = ET.fromstring(xml_text)
            for node in root.iter("node"):
                if node.get("resource-id") == "android:id/edit":
                    node.set("text", self._typed)
            with open(local_path, "w", encoding="utf-8") as fh:
                fh.write(ET.tostring(root, encoding="unicode"))
        return result

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


def test_configure_apn_waits_before_toggle_taps(monkeypatch):
    """2026-09-17, hypothesis-driven fix for a real, repeatable SOG07 MCC
    failure that persisted even with the confirmed coordinate and typing
    mechanism: a short delay must happen immediately before each pair of
    toggle taps, giving the on-screen keyboard's slide-in animation time
    to finish. Not yet confirmed as the actual fix on real hardware —
    see _KEYBOARD_TOGGLE_TAP_DELAY_SECONDS's docstring."""
    sleep_calls = []
    monkeypatch.setattr(
        "src.phase2.apn_setup.time.sleep", lambda seconds: sleep_calls.append(seconds)
    )
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    from src.phase2.apn_setup import _KEYBOARD_TOGGLE_TAP_DELAY_SECONDS

    # 4 fields, one delay before each field's pair of toggle taps.
    assert sleep_calls == [_KEYBOARD_TOGGLE_TAP_DELAY_SECONDS] * 4


def test_configure_apn_self_corrects_when_toggle_state_carries_over_between_fields(caplog):
    """Direct regression test for the client's real, diagnosed root cause
    (2026-09-17, SOG07): the toggle key's mode does NOT reset for each new
    field's dialog — it carries over from wherever the PREVIOUS field's
    typing left it, so a fixed "always tap exactly twice" can silently
    land in the wrong mode for a later field even though it worked for an
    earlier one.

    _CyclingKeyboardModeClient models a 3-state toggle, starting in a mode
    such that: field 1 (名前) coincidentally lands correct after the usual
    two taps, but every field after that starts from a carried-over state
    where two taps overshoots into the wrong mode — requiring exactly one
    single-tap correction (clear + retype) each time. All 4 fields must
    still be filled successfully, self-correcting via the
    read-back-and-retry loop rather than failing outright the way the old
    fixed-two-taps code did. (KEYBOARD_TOGGLE_PROFILE has no save-flow
    config, same as its other tests in this file — configure_apn() still
    returns False overall at the save step, which is expected and not
    what this test is checking.)

    Mode transitions depend only on toggle TAPS, not on what's typed, so
    the single-character-probe optimization (see the dedicated tests
    below — now applies to every field with a toggle configured, not just
    MCC/MNC) doesn't change how many attempts/taps any field needs here —
    only how much gets typed and cleared on a wrong one."""
    client = _CyclingKeyboardModeClient(
        ui_dumps=[LABELED_SCREEN_XML] * 40,
        toggle_coords=(106, 2239),
        cycle_length=3,
        starting_mode=1,
    )
    with caplog.at_level(logging.ERROR):
        configure_apn(client, KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    assert "could not be filled" not in caplog.text
    toggle_tap = "input tap 106 2239"
    # 名前: 2 taps (lands correct immediately). APN/MCC/MNC: 2 + 1 more
    # each (one single-tap correction apiece) = 3 each. 2 + 3*3 = 11.
    assert client.shell_calls.count(toggle_tap) == 11
    # Every field that needed correcting (APN, MCC, MNC) now only probes
    # with its OWN FIRST CHARACTER when wrong, not the whole value —
    # _CyclingKeyboardModeClient models one garbled "ガ" character per
    # wrong-mode `input text`/keyevent call regardless of how much was
    # actually typed, so each of the 3 corrected fields clears exactly 1
    # character = 3 DELs total.
    assert client.shell_calls.count("input keyevent KEYCODE_DEL") == 3
    # Confirms APN is genuinely probing with just its first character
    # ("r"), not retyping the whole "rakuten.jp" on the wrong attempt —
    # the real behavior this test exists to pin down.
    assert 'input text "r"' in client.shell_calls
    assert 'input text "akuten.jp"' in client.shell_calls
    assert 'input text "rakuten.jp"' not in client.shell_calls


def test_configure_apn_gives_up_after_max_toggle_attempts():
    """If the toggle never reaches the correct mode within
    _KEYBOARD_TOGGLE_MAX_ATTEMPTS, this must still fail loudly (with the
    existing cancel/navigate-up cleanup) rather than loop forever or
    silently accept a wrong value."""
    client = _CyclingKeyboardModeClient(
        ui_dumps=[LABELED_SCREEN_XML] * 40,
        toggle_coords=(106, 2239),
        # A cycle length longer than _KEYBOARD_TOGGLE_MAX_ATTEMPTS's total
        # reachable taps (2 for attempt 0, +1 per further attempt) means
        # 名前 can never land on the correct mode within the budget.
        cycle_length=100,
        starting_mode=1,
    )
    result = configure_apn(client, KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    assert result is False


def test_fill_labeled_field_numeric_probe_only_retypes_first_digit_on_wrong_attempt():
    """Efficiency fix (client feedback, 2026-09-17): retyping the WHOLE
    MCC/MNC value on every toggle-correction attempt was needlessly slow.
    Digits commit immediately per keystroke — no multi-key romaji
    composing delay the way letters can have — so only the value's own
    first digit needs probing to reveal the current mode; the rest is
    typed once, for real, only after that's confirmed correct."""
    client = _CyclingKeyboardModeClient(
        ui_dumps=[LABELED_SCREEN_XML] * 20,
        toggle_coords=(106, 2239),
        cycle_length=3,
        starting_mode=0,  # attempt 0's 2 taps land on mode 2 — wrong.
    )
    apn = {**LABELED_PROFILE.apn_settings(), "keyboard_mode_toggle_tap": [106, 2239]}
    result = _fill_labeled_field(client, apn, "MCC", "440", numeric_only=True)
    assert result is True
    # Exactly one corrective backspace — clearing the 1-character wrong
    # probe "ガ", never the full (wrongly-typed) 3-digit value.
    assert client.shell_calls.count("input keyevent KEYCODE_DEL") == 1
    # "4" (the probe, "440"[0]) is sent twice as the probe itself — once
    # wrong (attempt 0), once more after the correction (attempt 1) — then
    # a third time as part of "40" (the rest of the value, typed once for
    # real). "0" is typed exactly once, as part of that same rest — never
    # as part of any wrong attempt, since the probe alone was enough to
    # reveal the wrong mode without needing to type the whole value.
    assert client.shell_calls.count("input keyevent KEYCODE_4") == 3
    assert client.shell_calls.count("input keyevent KEYCODE_0") == 1


# Real finding (2026-09-18, client observation): Android auto-populates
# MCC/MNC from the SIM's own info when a new APN entry is created — very
# likely the actual root cause behind the whole SOG07 investigation (a
# hardcoded "11" from config/network.yaml was overwriting an
# already-correct, SIM-derived "10"). If the field already shows a real
# value, _fill_labeled_field() must trust it and skip typing entirely.
MCC_ALREADY_POPULATED_SCREEN_XML = LABELED_SCREEN_XML.replace(
    '<node resource-id="android:id/edit" bounds="[0,700][100,800]" />',
    '<node resource-id="android:id/edit" text="10" bounds="[0,700][100,800]" />',
)


def test_fill_labeled_field_skips_typing_when_numeric_field_already_populated():
    """If the device already shows a non-empty MCC/MNC value (auto-filled
    from the SIM), don't type over it — trust it, tap confirm, and
    return True with no toggle taps, no typing, no read-back retry of
    any kind."""
    client = EchoingFakeAdbClient(ui_dumps=[MCC_ALREADY_POPULATED_SCREEN_XML] * 20)
    apn = {**LABELED_PROFILE.apn_settings(), "keyboard_mode_toggle_tap": [106, 2239]}

    result = _fill_labeled_field(client, apn, "MCC", "440", numeric_only=True)

    assert result is True
    assert not any(c.startswith("input tap 106 2239") for c in client.shell_calls)
    assert not any(
        c.startswith("input text") or c.startswith("input keyevent KEYCODE_4")
        for c in client.shell_calls
    )
    # The confirm button (android:id/button1) must still be tapped.
    confirm_tap = "input tap {} {}".format((0 + 100) // 2, (800 + 900) // 2)
    assert confirm_tap in client.shell_calls


def test_fill_labeled_field_still_types_when_numeric_field_is_blank():
    """The skip only applies when the device shows a real value — a
    genuinely blank/未設定 field (real capture, SOG08, 2026-09-16) must
    still go through the normal type-and-verify path, since these fields
    are confirmed mandatory (real on-device validation, 2026-09-08)."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 20)
    apn = {**LABELED_PROFILE.apn_settings(), "keyboard_mode_toggle_tap": [106, 2239]}

    result = _fill_labeled_field(client, apn, "MCC", "440", numeric_only=True)

    assert result is True
    assert "input tap 106 2239" in client.shell_calls
    assert "input keyevent KEYCODE_4" in client.shell_calls


def test_fill_labeled_field_non_numeric_field_ignores_pre_existing_text():
    """The auto-populate skip is scoped to numeric_only fields only —
    Android doesn't auto-fill 名前/APN from anything, so a non-empty
    edit_field there (e.g. leftover text from a previous attempt) must
    NOT be trusted; 名前/APN always go through the normal path."""
    screen = LABELED_SCREEN_XML.replace(
        '<node resource-id="android:id/edit" bounds="[0,700][100,800]" />',
        '<node resource-id="android:id/edit" text="leftover" bounds="[0,700][100,800]" />',
    )
    client = EchoingFakeAdbClient(ui_dumps=[screen] * 20)
    apn = {**LABELED_PROFILE.apn_settings(), "keyboard_mode_toggle_tap": [106, 2239]}

    result = _fill_labeled_field(client, apn, "名前", "rakuten.jp", numeric_only=False)

    assert result is True
    assert "input tap 106 2239" in client.shell_calls


def test_fill_labeled_field_text_probe_only_retypes_first_character_on_wrong_attempt():
    """Extended, same day (client feedback from watching real SOG07
    hardware): 名前/APN were observed retyping the WHOLE value on a wrong
    attempt, same as MCC/MNC used to. The probe optimization now applies
    to every field with a toggle configured, not just numeric ones — this
    pins down that 名前 only retypes/clears its first character ("r"),
    never the whole "rakuten.jp", on a wrong attempt."""
    client = _CyclingKeyboardModeClient(
        ui_dumps=[LABELED_SCREEN_XML] * 20,
        toggle_coords=(106, 2239),
        cycle_length=3,
        starting_mode=0,  # attempt 0's 2 taps land on mode 2 — wrong.
    )
    apn = {**LABELED_PROFILE.apn_settings(), "keyboard_mode_toggle_tap": [106, 2239]}
    result = _fill_labeled_field(client, apn, "名前", "rakuten.jp", numeric_only=False)
    assert result is True
    assert 'input text "r"' in client.shell_calls
    assert 'input text "akuten.jp"' in client.shell_calls
    assert 'input text "rakuten.jp"' not in client.shell_calls
    # Exactly one corrective backspace — clearing the 1-character wrong
    # probe, never the full (wrongly-typed) 10-character value.
    assert client.shell_calls.count("input keyevent KEYCODE_DEL") == 1


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


# SOG07 (2026-09-17, second finding same day): even with the correct
# numeric-keypad toggle coordinate confirmed and applied, a live run kept
# failing MCC — the toggle only actually took effect for input_text_direct()
# on this keypad, not input_digits_direct()'s per-keyevent mechanism.
# use_text_entry_for_numeric switches MCC/MNC to input_text_direct().
TEXT_ENTRY_NUMERIC_PROFILE = ModelProfile(
    {
        "model": "SOG07-like Numeric-Text-Entry Test",
        "model_number": "TST10",
        "manufacturer": "Test",
        "android_version": 14,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            **NUMERIC_KEYBOARD_TOGGLE_PROFILE.apn_settings(),
            "use_text_entry_for_numeric": True,
        },
    }
)


def test_configure_apn_use_text_entry_for_numeric_types_mcc_mnc_via_input_text():
    """With the flag set, MCC/MNC must be typed via `input text`, not
    per-digit keyevents. Sent as two separate calls — a single-digit
    probe ("4"/"1"), then the rest of the value ("40"/"1") — per the
    2026-09-17 probe optimization, rather than one combined call; a real
    device's `input text` appends at the cursor, so these two calls
    together still commit the full "440"/"11"."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, TEXT_ENTRY_NUMERIC_PROFILE, "rakuten.jp", "440", "11")
    assert 'input text "4"' in client.shell_calls
    assert 'input text "40"' in client.shell_calls
    assert 'input text "1"' in client.shell_calls
    assert "input keyevent KEYCODE_4" not in client.shell_calls


def test_configure_apn_use_text_entry_for_numeric_is_opt_in():
    """Without the flag (NUMERIC_KEYBOARD_TOGGLE_PROFILE), MCC/MNC must
    keep using the original per-digit keyevent mechanism, proven correct
    on SHG10/SHG07."""
    client = EchoingFakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, NUMERIC_KEYBOARD_TOGGLE_PROFILE, "rakuten.jp", "440", "11")
    assert "input keyevent KEYCODE_4" in client.shell_calls
    assert 'input text "440"' not in client.shell_calls


# A test pinning down a post-read-back, pre-confirm delay for
# use_text_entry_for_numeric fields lived here briefly (2026-09-18) —
# removed the same day once the client retested on real SOG07 hardware
# and the hypothesis it was checking (an uncommitted IME composing span
# at confirm-time) turned out not to be the actual cause. See
# docs/record.md's SOG07 section for what's actually being investigated
# now.


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


# --- reach_via_wifi_settings_intent (real, SHG07/SHG10, 2026-09-18) --------
# android.settings.APN_SETTINGS turned out to reach a non-authoritative APN
# context — real client testing showed saves made there never appeared on
# the APN list reached by manually navigating through the SIM's own carrier
# settings. See apn_setup.py's _navigate_apn_menu() docstring.

WIFI_SETTINGS_NAV_SCREEN_XML = """<hierarchy>
  <node resource-id="com.android.settings:id/settings_button" bounds="[0,0][100,100]" />
  <node resource-id="android:id/title" text="アクセス ポイント名" bounds="[0,100][100,200]" />
  <node content-desc="アクセスポイント名" bounds="[0,200][1080,300]" />
  <node resource-id="android:id/title" text="名前" bounds="[0,300][100,400]" />
  <node resource-id="android:id/title" text="APN" bounds="[0,400][100,500]" />
  <node resource-id="android:id/title" text="MCC" bounds="[0,500][100,600]" />
  <node resource-id="android:id/title" text="MNC" bounds="[0,600][100,700]" />
  <node resource-id="android:id/edit" bounds="[0,700][100,800]" />
  <node resource-id="android:id/button1" bounds="[0,800][100,900]" />
</hierarchy>"""

WIFI_SETTINGS_NAV_PROFILE = ModelProfile(
    {
        "model": "SHG07-like WIFI_SETTINGS-nav Test",
        "model_number": "TST12",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {
            **LABELED_PROFILE.apn_settings(),
            "reach_via_wifi_settings_intent": True,
            "menu_path": [
                {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
                {"type": "text", "value": "アクセス ポイント名"},
            ],
        },
    }
)


def test_configure_apn_reaches_list_via_wifi_settings_intent_and_menu_path():
    """With reach_via_wifi_settings_intent set, navigation must use
    android.settings.WIFI_SETTINGS (never APN_SETTINGS), then complete
    the full menu_path (gear icon, then the real "アクセス ポイント名"
    tap) before field-filling starts."""
    client = FakeAdbClient(ui_dumps=[WIFI_SETTINGS_NAV_SCREEN_XML] * 30)

    result = configure_apn(client, WIFI_SETTINGS_NAV_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    assert "am start -a android.settings.WIFI_SETTINGS" in client.shell_calls
    assert "am start -a android.settings.APN_SETTINGS" not in client.shell_calls
    gear_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    final_tap = "input tap {} {}".format((0 + 100) // 2, (100 + 200) // 2)
    assert gear_tap in client.shell_calls
    assert final_tap in client.shell_calls
    # Positive proof landing was recognized and field-filling proceeded.
    name_field_tap = "input tap {} {}".format((0 + 100) // 2, (300 + 400) // 2)
    assert name_field_tap in client.shell_calls


def test_configure_apn_wifi_settings_nav_fails_loudly_if_intent_errors():
    """If the WIFI_SETTINGS intent itself fails, this path has no
    fallback (unlike the original APN_SETTINGS path) — must fail loudly
    rather than silently trying something else."""

    class NoIntentClient(FakeAdbClient):
        def shell(self, command, timeout=30):
            if command == "am start -a android.settings.WIFI_SETTINGS":
                from src.device.adb_client import AdbCommandError
                raise AdbCommandError(command, "intent not supported on this build")
            return super().shell(command, timeout=timeout)

    client = NoIntentClient(ui_dumps=[WIFI_SETTINGS_NAV_SCREEN_XML] * 30)

    result = configure_apn(client, WIFI_SETTINGS_NAV_PROFILE, "rakuten.jp", "440", "11")

    assert result is False
    assert not any(c.startswith("input tap") for c in client.shell_calls)


def test_configure_apn_scrolls_before_tapping_the_final_sim_scoped_step():
    """Real finding (2026-09-18): "アクセス ポイント名" sits right at the
    very bottom edge of the carrier-settings screen on every real device
    checked so far, risking a tap swallowed by the system
    navigation/gesture bar. Must scroll down once before tapping it, same
    defensive pattern as MCC/MNC's below-the-fold field rows."""
    client = FakeAdbClient(ui_dumps=[WIFI_SETTINGS_NAV_SCREEN_XML] * 30)

    configure_apn(client, WIFI_SETTINGS_NAV_PROFILE, "rakuten.jp", "440", "11")

    gear_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    final_tap = "input tap {} {}".format((0 + 100) // 2, (100 + 200) // 2)
    swipe = next((c for c in client.shell_calls if c.startswith("input swipe")), None)
    assert swipe is not None
    # Order matters: gear icon, THEN scroll, THEN the final tap — not
    # scrolling before the gear icon (which hasn't been reached yet) or
    # after the final tap (too late to help).
    assert (
        client.shell_calls.index(gear_tap)
        < client.shell_calls.index(swipe)
        < client.shell_calls.index(final_tap)
    )


def test_configure_apn_reach_via_wifi_settings_rejects_non_text_final_step():
    """reach_via_wifi_settings_intent's menu_path must end with a
    {'type': 'text', ...} step — anything else is a real config mistake
    that should fail loudly at the point of use, not silently misbehave."""
    bad_profile = ModelProfile(
        {
            "model": "Bad Test",
            "model_number": "TST13",
            "manufacturer": "Test",
            "android_version": 13,
            "wizard_steps": [{"screen": "x", "resource_id": "y", "action": "tap"}],
            "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
            "apn_settings": {
                **LABELED_PROFILE.apn_settings(),
                "reach_via_wifi_settings_intent": True,
                "menu_path": [
                    {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
                    {"type": "resource_id", "value": "not.a.text.step"},
                ],
            },
        }
    )
    client = FakeAdbClient(ui_dumps=[WIFI_SETTINGS_NAV_SCREEN_XML] * 30)
    with pytest.raises(ValueError):
        configure_apn(client, bad_profile, "rakuten.jp", "440", "11")


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


def test_configure_apn_gives_up_softly_without_any_renavigation(monkeypatch, caplog):
    """REMOVED, 2026-09-18 (client feedback): a third tier used to
    force-stop Settings and fully re-navigate (through
    _navigate_apn_menu()'s intermediate screens) when the delay+re-dump
    still didn't find the entry. A client watching the screen saw this as
    a confusing round-trip — the device visibly left the just-reached
    APN list, flashed through the intermediate navigation screens, and
    landed back on it again — whose diagnostic value didn't justify the
    disruption. This pins down that it's really gone: if the delay+re-dump
    still doesn't find the entry, configure_apn() must now just log the
    soft warning and return True, with NO further navigation of any
    kind — the device stays exactly where it already was, right after
    保存."""
    monkeypatch.setattr("src.phase2.apn_setup.time.sleep", lambda _seconds: None)
    client = ApnPostSaveDelayedVisibilityClient(
        ui_dumps=[SAVE_FLOW_SCREEN_XML] * 30,
        post_save_xml=POST_SAVE_NOT_YET_REFRESHED_XML,
        # Never actually refreshes even after the one delay+re-dump retry
        # — the entry simply never becomes visible on this same screen.
        delayed_post_save_xml=POST_SAVE_NOT_YET_REFRESHED_XML,
    )

    with caplog.at_level(logging.WARNING, logger="src.phase2.apn_setup"):
        result = configure_apn(client, SAVE_FLOW_PROFILE, "rakuten.jp", "440", "11")

    assert result is True
    messages = [r.getMessage() for r in caplog.records]
    assert any("wasn't spotted" in m for m in messages)
    # No re-navigation of any kind after the save tap — no force-stop, no
    # second APN_SETTINGS/WIFI_SETTINGS intent.
    assert "am force-stop com.android.settings" not in client.shell_calls
    assert client.shell_calls.count("am start -a android.settings.APN_SETTINGS") == 1
    assert "am start -a android.settings.WIFI_SETTINGS" not in client.shell_calls


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
