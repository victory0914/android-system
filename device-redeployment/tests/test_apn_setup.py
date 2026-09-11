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

from src.device.model_profile import ModelProfile
from src.phase2.apn_setup import configure_apn
from tests.fakes import FakeAdbClient

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
    client = FakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
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


class ScrollRevealsMncClient(FakeAdbClient):
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


class ApnPostSaveClient(FakeAdbClient):
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
        return FakeAdbClient.pull(self, remote_path, local_path)


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
