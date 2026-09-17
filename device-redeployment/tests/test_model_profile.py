"""Tests for src/device/model_profile.py against the four real model YAML
files shipped in config/models/."""

from pathlib import Path

import pytest

from src.device.model_profile import ModelProfile, ModelProfileError

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "config" / "models"

# Wizard shape and APN shape are independent axes in this schema (see
# model_profile.py: has_screen_driven_wizard() only looks at "wizard" vs.
# "wizard_steps"; apn_setup.py separately branches on
# "field_row_resource_id" in apn_settings) — as of 2026-09-16 every model
# uses the labeled APN shape (real dumps for all 4 confirm the same
# generic-row-id/label pattern, see docs/record.md), but only SHG10/SHG07
# have a screen-driven wizard (photograph-derived, from real client OOBE
# photos of that specific lineup) — SOG07/SOG08 still carry Stage A's
# from-scratch wizard_steps placeholders, since no wizard data of any kind
# (photos or otherwise) exists for either.
LEGACY_WIZARD_MODEL_FILES = [
    "sony_xperia_ace3.yaml",
    "sony_xperia_10iv.yaml",
]
SCREEN_DRIVEN_WIZARD_MODEL_FILES = ["sharp_aquos_sense7.yaml", "sharp_aquos_sense6s.yaml"]
MODEL_FILES = LEGACY_WIZARD_MODEL_FILES + SCREEN_DRIVEN_WIZARD_MODEL_FILES

EXPECTED_MODEL_NUMBERS = {"SOG08", "SOG07", "SHG07", "SHG10"}


@pytest.mark.parametrize("filename", LEGACY_WIZARD_MODEL_FILES)
def test_load_each_legacy_wizard_model_file(filename):
    """SOG07/SOG08's wizard_steps remain 100% Stage A placeholders — no
    wizard/OOBE data exists for either (see docs/record.md's "Wizard
    capture — RESOLVED AS NOT REMOTELY POSSIBLE"; unlike SHG10, there are
    also no client photos of either unit's OOBE flow to derive a
    screen-driven config from)."""
    profile = ModelProfile.load(str(MODELS_DIR / filename))

    assert isinstance(profile.model, str) and profile.model
    assert isinstance(profile.model_number, str) and profile.model_number
    assert isinstance(profile.manufacturer, str) and profile.manufacturer
    assert isinstance(profile.android_version, int)
    assert profile.has_screen_driven_wizard() is False

    steps = profile.wizard_steps()
    assert isinstance(steps, list) and len(steps) > 0
    for step in steps:
        assert isinstance(step["screen"], str)
        assert isinstance(step["resource_id"], str)
        assert isinstance(step["action"], str)
        if "optional" in step:
            assert isinstance(step["optional"], bool)


@pytest.mark.parametrize("filename", MODEL_FILES)
def test_load_each_model_file_uses_labeled_apn_shape(filename):
    """As of 2026-09-16, all four models use the same labeled APN shape —
    real dumps for every one confirm field rows share one generic
    resource-id, disambiguated only by label text (see docs/record.md).
    This just confirms every file parses into that shape; the
    model-specific tests below check the actual real values."""
    profile = ModelProfile.load(str(MODELS_DIR / filename))

    wifi = profile.wifi_settings()
    assert isinstance(wifi["toggle_resource_id"], str)
    assert isinstance(wifi["network_list_resource_id"], str)
    assert isinstance(wifi["menu_path"], list) and len(wifi["menu_path"]) > 0

    apn = profile.apn_settings()
    assert isinstance(apn["field_row_resource_id"], str)
    assert isinstance(apn["name_field_label"], str)
    assert isinstance(apn["apn_field_label"], str)
    assert isinstance(apn["mcc_field_label"], str)
    assert isinstance(apn["mnc_field_label"], str)


def test_load_shg10_model_file_screen_driven_wizard_and_labeled_apn_fields():
    """SHG10 (Stage B — real device data, docs/record.md) uses a different
    wizard shape than the 2 legacy-wizard models: screen-driven, from real
    client OOBE photos of this specific unit."""
    profile = ModelProfile.load(str(MODELS_DIR / "sharp_aquos_sense7.yaml"))

    assert profile.model_number == "SHG10"
    assert profile.has_screen_driven_wizard() is True

    screens = profile.wizard_screens()
    assert isinstance(screens, list) and len(screens) > 0
    for screen in screens:
        assert isinstance(screen["name"], str)
        assert isinstance(screen["identify_by_text"], str)
        assert isinstance(screen["action"], str)

    wifi = profile.wifi_settings()
    assert wifi["toggle_resource_id"] == "android:id/switch_widget"
    assert wifi["network_list_resource_id"] == "android:id/title"
    assert isinstance(wifi["menu_path"], list) and len(wifi["menu_path"]) > 0

    apn = profile.apn_settings()
    assert apn["field_row_resource_id"] == "android:id/title"
    assert apn["name_field_label"] == "名前"
    assert apn["apn_field_label"] == "APN"
    # RESOLVED (real, 2026-09-18): android.settings.APN_SETTINGS turned
    # out to reach a non-authoritative APN context — see
    # apn_setup.py's _navigate_apn_menu() docstring. Applied here on the
    # same lineage-inheritance basis as SHG07's independent confirmation.
    assert apn["reach_via_wifi_settings_intent"] is True
    assert apn["menu_path"] == [
        {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
        {"type": "text", "value": "アクセス ポイント名"},
    ]
    # MCC/MNC DO exist on this build (settles docs/record.md's open
    # question) — must not have been deleted from the schema.
    assert apn["mcc_field_label"] == "MCC"
    assert apn["mnc_field_label"] == "MNC"
    # Genuinely unresolved — must stay None, not a guessed value.
    assert apn["add_button_resource_id"] is None
    # Save is real, resolved data now (confirmed on-device, 2026-09-08): a
    # two-tap overflow-menu flow, not a literal save button — the legacy
    # single-button field stays None on this model on purpose.
    assert apn["save_button_resource_id"] is None
    assert apn["overflow_menu_content_desc"] == "その他のオプション"
    assert apn["save_menu_item_text"] == "保存"
    # Briefly set to true (2026-09-15, "same input method across every
    # device"), then reverted the same day once round 2 of the SHG07
    # investigation proved per-keyevent typing isn't actually
    # IME-bypassing for letters either (see docs/record.md) — keeping it
    # here bought no real safety and only risked reproducing SHG07's
    # failure on a path already proven working. Unset — SHG10 uses
    # input_text_direct() for 名前/APN exactly as it did on 2026-09-11.
    assert apn.get("use_keyevent_text_entry") is None
    # RESOLVED (real, 2026-09-17): a parallel 4-device run showed SHG10
    # was never actually immune to the かな-conversion symptom — its
    # keyboard just happened to be in alphanumeric mode during the
    # 2026-09-11 test. This device's own confirmed coordinate.
    assert apn["keyboard_mode_toggle_tap"] == [119, 2223]


@pytest.mark.parametrize("filename", SCREEN_DRIVEN_WIZARD_MODEL_FILES)
def test_load_each_screen_driven_wizard_model_file(filename):
    """Both SHG10 (real device data) and SHG07 (inherited from SHG10,
    2026-09-14) use the same wizard schema shape."""
    profile = ModelProfile.load(str(MODELS_DIR / filename))

    assert isinstance(profile.model, str) and profile.model
    assert isinstance(profile.model_number, str) and profile.model_number
    assert isinstance(profile.manufacturer, str) and profile.manufacturer
    assert isinstance(profile.android_version, int)
    assert profile.has_screen_driven_wizard() is True

    screens = profile.wizard_screens()
    assert isinstance(screens, list) and len(screens) > 0
    for screen in screens:
        assert isinstance(screen["name"], str)
        assert isinstance(screen["identify_by_text"], str)
        assert isinstance(screen["action"], str)


def test_load_shg07_model_file_inherited_from_shg10():
    """SHG07 (AQUOS sense6s, Android 13) was switched from Stage A's
    from-scratch legacy guesses to SHG10's real, confirmed values on
    2026-09-14, at the client's request, on the reasoning that SHG07 and
    SHG10 are the same SHARP AQUOS lineup — real for SHG10, NOT
    independently confirmed for SHG07. This test pins down that the
    values are exactly SHG10's (the point of inheriting them), and that
    SHG07 keeps its own identity fields — it does not become SHG10."""
    profile = ModelProfile.load(str(MODELS_DIR / "sharp_aquos_sense6s.yaml"))

    assert profile.model_number == "SHG07"
    assert profile.model == "AQUOS sense6s"
    assert profile.android_version == 13  # unchanged — still SHG07's own value

    wifi = profile.wifi_settings()
    assert wifi["toggle_resource_id"] == "android:id/switch_widget"
    assert wifi["network_list_resource_id"] == "android:id/title"
    assert wifi["connect_button_text"] == "接続"

    apn = profile.apn_settings()
    assert apn["field_row_resource_id"] == "android:id/title"
    assert apn["name_field_label"] == "名前"
    assert apn["apn_field_label"] == "APN"
    assert apn["mcc_field_label"] == "MCC"
    assert apn["mnc_field_label"] == "MNC"
    assert apn["dialog_edit_field_resource_id"] == "android:id/edit"
    assert apn["dialog_confirm_button_resource_id"] == "android:id/button1"
    assert apn["add_button_resource_id"] is None
    assert apn["add_button_content_desc"] == "新しい APN"
    assert apn["overflow_menu_content_desc"] == "その他のオプション"
    assert apn["save_menu_item_text"] == "保存"
    # RESOLVED — real, directly confirmed ON SHG07 ITSELF (2026-09-18, a
    # real dump of the carrier mobile-network-settings screen) —
    # android.settings.APN_SETTINGS reaches a non-authoritative APN
    # context; see apn_setup.py's _navigate_apn_menu() docstring.
    assert apn["reach_via_wifi_settings_intent"] is True
    assert apn["menu_path"] == [
        {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
        {"type": "text", "value": "アクセス ポイント名"},
    ]
    # Briefly real SHG07 data (2026-09-14: found the active IME interferes
    # with plain `input text` for 名前/APN), then reverted 2026-09-15 once
    # round 2 proved per-keyevent typing (the fix this enabled) fails the
    # exact same way — 「らくてん。」 from "rakuten.jp" — since both `input
    # text` and `input keyevent` are equally exposed to the keyboard's
    # current mode. SHG07 now uses the same method as SHG10 (unset here
    # too) for a direct, apples-to-apples real-hardware comparison.
    assert apn.get("use_keyevent_text_entry") is None
    # RESOLVED — real, directly confirmed 2026-09-15 (Pointer Location +
    # a scripted `adb shell input tap` verification, not a screenshot
    # estimate). Tied to this exact unit's screen resolution — see
    # ui_automator.py's tap_at_coordinates() and docs/record.md.
    assert apn["keyboard_mode_toggle_tap"] == [106, 2239]


def test_load_sog07_model_file_real_apn_and_wifi_data():
    """SOG07 (Xperia 10 IV, Android 14) got real wifi_settings/apn_settings
    data on 2026-09-16 from client-supplied dumps — see docs/record.md.
    Notably byte-identical to SHG10's real values for every id/content-desc
    checked (a different manufacturer), confirming this is the plain,
    unskinned AOSP Settings APN editor, not something OEM-specific."""
    profile = ModelProfile.load(str(MODELS_DIR / "sony_xperia_10iv.yaml"))

    assert profile.model_number == "SOG07"
    assert profile.model == "Xperia 10 IV"
    assert profile.android_version == 14
    # Wizard is untouched Stage A — no real/inherited wizard data exists.
    assert profile.has_screen_driven_wizard() is False

    wifi = profile.wifi_settings()
    assert wifi["toggle_resource_id"] == "android:id/switch_widget"
    assert wifi["network_list_resource_id"] == "android:id/title"
    # Real, confirmed difference from SHG10: this screen's title is
    # "インターネット" via content-desc, not SHARP's "Wi-Fi とモバイルネットワーク".
    assert {"type": "text", "value": "インターネット"} in wifi["menu_path"]

    apn = profile.apn_settings()
    assert apn["field_row_resource_id"] == "android:id/title"
    assert apn["name_field_label"] == "名前"
    assert apn["apn_field_label"] == "APN"
    assert apn["mcc_field_label"] == "MCC"
    assert apn["mnc_field_label"] == "MNC"
    assert apn["dialog_edit_field_resource_id"] == "android:id/edit"
    assert apn["dialog_confirm_button_resource_id"] == "android:id/button1"
    assert apn["dialog_cancel_button_resource_id"] == "android:id/button2"
    assert apn["add_button_resource_id"] is None
    assert apn["add_button_content_desc"] == "新しい APN"
    assert apn["overflow_menu_content_desc"] == "その他のオプション"
    assert apn["save_menu_item_text"] == "保存"
    assert apn["navigate_up_content_desc"] == "上へ移動"
    # RESOLVED (real, 2026-09-17): a live run showed the same
    # kana-conversion IME symptom SHG07 had. This is this device's own
    # Pointer-Location-confirmed coordinate, not inherited from SHG07's.
    assert apn["keyboard_mode_toggle_tap"] == [145, 2308]
    # RESOLVED (real, 2026-09-17): MCC/MNC open a genuinely different
    # numeric keypad on this device — its own toggle key sits at a
    # different X than the text keyboard's, confirmed independently.
    assert apn["keyboard_mode_toggle_tap_numeric"] == [93, 2300]
    # RESOLVED (real, 2026-09-17, same-day second finding): even with the
    # coordinate above, a live run kept failing MCC — the toggle only
    # actually worked for input_text_direct(), not per-digit keyevents.
    assert apn["use_text_entry_for_numeric"] is True
    # RESOLVED, 2026-09-18: android.settings.APN_SETTINGS reaches a
    # non-authoritative APN context — see apn_setup.py's
    # _navigate_apn_menu() docstring. NOT independently confirmed on
    # THIS unit; inherited from SOG08's own real confirmation, same
    # manufacturer/lineup.
    assert apn["reach_via_wifi_settings_intent"] is True
    assert apn["menu_path"] == [
        {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
        {"type": "text", "value": "アクセス ポイント名"},
    ]


def test_load_sog08_model_file_real_apn_and_wifi_data():
    """SOG08 (Xperia Ace III, Android 13) got the same treatment as SOG07,
    same day, from its own real dumps."""
    profile = ModelProfile.load(str(MODELS_DIR / "sony_xperia_ace3.yaml"))

    assert profile.model_number == "SOG08"
    assert profile.model == "Xperia Ace III"
    assert profile.android_version == 13
    assert profile.has_screen_driven_wizard() is False

    wifi = profile.wifi_settings()
    assert wifi["toggle_resource_id"] == "android:id/switch_widget"
    assert wifi["network_list_resource_id"] == "android:id/title"
    assert {"type": "text", "value": "インターネット"} in wifi["menu_path"]

    apn = profile.apn_settings()
    assert apn["field_row_resource_id"] == "android:id/title"
    assert apn["name_field_label"] == "名前"
    assert apn["apn_field_label"] == "APN"
    assert apn["mcc_field_label"] == "MCC"
    assert apn["mnc_field_label"] == "MNC"
    assert apn["dialog_edit_field_resource_id"] == "android:id/edit"
    assert apn["dialog_confirm_button_resource_id"] == "android:id/button1"
    assert apn["dialog_cancel_button_resource_id"] == "android:id/button2"
    assert apn["add_button_resource_id"] is None
    assert apn["add_button_content_desc"] == "新しい APN"
    assert apn["overflow_menu_content_desc"] == "その他のオプション"
    assert apn["save_menu_item_text"] == "保存"
    assert apn["navigate_up_content_desc"] == "上へ移動"
    # RESOLVED (real, 2026-09-17): same symptom, same fix, this device's
    # own confirmed coordinate.
    assert apn["keyboard_mode_toggle_tap"] == [73, 1352]
    # RESOLVED — real, directly confirmed ON SOG08 ITSELF (2026-09-18, a
    # real dump of its own carrier mobile-network-settings screen,
    # mobile_network_SOG08.xml): android.settings.APN_SETTINGS reaches a
    # non-authoritative APN context; see apn_setup.py's
    # _navigate_apn_menu() docstring.
    assert apn["reach_via_wifi_settings_intent"] is True
    assert apn["menu_path"] == [
        {"type": "resource_id", "value": "com.android.settings:id/settings_button"},
        {"type": "text", "value": "アクセス ポイント名"},
    ]


def test_load_all_keys_by_model_number():
    profiles = ModelProfile.load_all(str(MODELS_DIR))
    assert set(profiles.keys()) == EXPECTED_MODEL_NUMBERS
    for model_number, profile in profiles.items():
        assert profile.model_number == model_number


def test_manufacturers_match_expected():
    profiles = ModelProfile.load_all(str(MODELS_DIR))
    assert profiles["SOG08"].manufacturer == "Sony"
    assert profiles["SOG07"].manufacturer == "Sony"
    assert profiles["SHG07"].manufacturer == "SHARP"
    assert profiles["SHG10"].manufacturer == "SHARP"


def test_android_versions_match_expected():
    profiles = ModelProfile.load_all(str(MODELS_DIR))
    assert profiles["SOG08"].android_version == 13
    assert profiles["SOG07"].android_version == 14
    assert profiles["SHG07"].android_version == 13
    # Corrected in Stage B: the original spec assumed Android 12 for this
    # model, but `adb` against the real unit reported Android 14
    # ("[SHARP] KDDI SHG10 (Android 14)" — see docs/record.md).
    assert profiles["SHG10"].android_version == 14


def test_missing_required_field_raises(tmp_path):
    bad_yaml = tmp_path / "broken.yaml"
    bad_yaml.write_text(
        "model: \"Broken Phone\"\n"
        "model_number: \"BRK01\"\n"
        "manufacturer: \"Nobody\"\n"
        # android_version deliberately omitted
        "wizard_steps:\n"
        "  - screen: \"x\"\n"
        "    resource_id: \"y\"\n"
        "    action: \"tap\"\n"
        "wifi_settings:\n"
        "  toggle_resource_id: \"a\"\n"
        "  network_list_resource_id: \"b\"\n"
        "apn_settings:\n"
        "  menu_path: [\"Settings\"]\n"
        "  name_field_resource_id: \"c\"\n"
        "  apn_field_resource_id: \"d\"\n"
        "  save_button_resource_id: \"e\"\n",
        encoding="utf-8",
    )
    with pytest.raises(ModelProfileError):
        ModelProfile.load(str(bad_yaml))
