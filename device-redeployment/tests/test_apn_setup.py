"""Tests for src/phase2/apn_setup.py — both the legacy literal-resource-id
field shape (still used by the 3 models untouched by Stage B) and the new
label-based field shape (SHG10 — real field rows share one generic
resource-id, disambiguated by label text; see docs/record.md), plus the
android.settings.WIFI_SETTINGS intent shortcut added after a real
client-PC run showed menu_path's leading text steps (e.g. tapping "設定")
fail whenever the device isn't already on a screen where that text is
visible."""

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
                {"type": "text", "value": "アクセスポイント名"},
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

# One dump reused for every step: navigation targets, all four field rows
# (by label), the best-guess dialog edit/confirm ids. Real automation would
# re-dump between taps, but since none of these targets disappear from this
# synthetic fixture, one dump satisfies every lookup FakeAdbClient repeats.
LABELED_SCREEN_XML = """<hierarchy>
  <node text="設定" bounds="[0,0][100,100]" />
  <node resource-id="com.android.settings:id/settings_button" bounds="[0,100][100,200]" />
  <node text="アクセスポイント名" bounds="[0,200][100,300]" />
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
    client = FakeAdbClient(ui_dumps=[LABELED_SCREEN_XML] * 30)
    configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")
    injected = [c for c in client.shell_calls if "ADB_INPUT_TEXT" in c]
    assert any("rakuten.jp" in c for c in injected)
    assert any("440" in c for c in injected)
    assert any("11" in c for c in injected)


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


def test_configure_apn_intent_shortcut_skips_leading_text_steps():
    """When the WIFI_SETTINGS intent lands somewhere the first non-text
    menu_path step (the settings_button icon) is already reachable, the
    leading "設定" text tap must be skipped entirely."""
    # Only the post-intent screen is provided — settings_button IS present,
    # "設定" text is NOT. If the code tried to tap "設定" first (i.e. didn't
    # skip it), navigation would fail outright since it's absent here.
    screen_without_settings_text = LABELED_SCREEN_XML.replace(
        '<node text="設定" bounds="[0,0][100,100]" />', ""
    )
    client = FakeAdbClient(ui_dumps=[screen_without_settings_text] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    # Reaches the (unresolved) save step, not stuck at navigation.
    assert result is False
    assert any(c == "am start -a android.settings.WIFI_SETTINGS" for c in client.shell_calls)
    settings_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    assert settings_tap not in client.shell_calls


def test_configure_apn_falls_back_to_full_menu_path_when_intent_command_fails():
    class NoIntentClient(FakeAdbClient):
        def shell(self, command, timeout=30):
            if command == "am start -a android.settings.WIFI_SETTINGS":
                from src.device.adb_client import AdbCommandError
                raise AdbCommandError(command, "intent not supported on this build")
            return super().shell(command, timeout=timeout)

    client = NoIntentClient(ui_dumps=[LABELED_SCREEN_XML] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    settings_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    assert settings_tap in client.shell_calls


def test_configure_apn_falls_back_to_full_menu_path_when_intent_lands_elsewhere():
    home_screen_xml = '<hierarchy><node text="Home" bounds="[0,0][10,10]" /></hierarchy>'
    client = FakeAdbClient(ui_dumps=[home_screen_xml, LABELED_SCREEN_XML] + [LABELED_SCREEN_XML] * 30)

    result = configure_apn(client, LABELED_PROFILE, "rakuten.jp", "440", "11")

    assert result is False  # still fails at the (unresolved) save step, not navigation
    settings_tap = "input tap {} {}".format((0 + 100) // 2, (0 + 100) // 2)
    assert settings_tap in client.shell_calls


def test_configure_apn_all_text_menu_path_never_attempts_intent():
    """A menu_path with no non-text steps at all (the legacy shape) has no
    shared-prefix opportunity to skip — the intent must never even be
    tried, matching Stage A's original behavior exactly."""
    client = FakeAdbClient(ui_dumps=[LEGACY_SCREEN_XML] * 10)
    configure_apn(client, LEGACY_PROFILE, "internet", "310", "260")
    assert not any(c == "am start -a android.settings.WIFI_SETTINGS" for c in client.shell_calls)


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
