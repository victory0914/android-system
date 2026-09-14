"""Tests for src/device/model_profile.py against the four real model YAML
files shipped in config/models/."""

from pathlib import Path

import pytest

from src.device.model_profile import ModelProfile, ModelProfileError

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "config" / "models"

# The 2 Sony models remain fully untouched — Stage A's legacy,
# resource-id-based schema throughout, no real device data at all. SHG10
# was updated with real device data (see docs/record.md) and uses the
# newer screen-driven wizard schema plus label-based APN fields — validated
# separately below. SHG07 was switched to the same schema on 2026-09-14,
# populated with values *inherited* from SHG10 (same SHARP AQUOS lineup) at
# the client's request, rather than the 3 untouched models' from-scratch
# guesses — real, but for a different device, not independently confirmed
# for SHG07 itself. See config/models/sharp_aquos_sense6s.yaml's file-level
# comment and PENDING_REAL_DEVICE_DATA.md.
LEGACY_MODEL_FILES = [
    "sony_xperia_ace3.yaml",
    "sony_xperia_10iv.yaml",
]
SCREEN_DRIVEN_MODEL_FILES = ["sharp_aquos_sense7.yaml", "sharp_aquos_sense6s.yaml"]
MODEL_FILES = LEGACY_MODEL_FILES + SCREEN_DRIVEN_MODEL_FILES

EXPECTED_MODEL_NUMBERS = {"SOG08", "SOG07", "SHG07", "SHG10"}


@pytest.mark.parametrize("filename", LEGACY_MODEL_FILES)
def test_load_each_legacy_model_file(filename):
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

    wifi = profile.wifi_settings()
    assert isinstance(wifi["toggle_resource_id"], str)
    assert isinstance(wifi["network_list_resource_id"], str)

    apn = profile.apn_settings()
    assert isinstance(apn["menu_path"], list) and len(apn["menu_path"]) > 0
    assert isinstance(apn["name_field_resource_id"], str)
    assert isinstance(apn["apn_field_resource_id"], str)
    assert isinstance(apn["save_button_resource_id"], str)


def test_load_shg10_model_file_screen_driven_wizard_and_labeled_apn_fields():
    """SHG10 (Stage B — real device data, docs/record.md) uses a different
    shape than the 3 legacy models: screen-driven wizard, label-based APN
    fields (real dumps showed no per-field resource-id exists), and two
    genuinely-unresolved fields (add/save) left as None rather than guessed."""
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
    # Client request (2026-09-15): same input method across every device —
    # SHG10 now opts into the same keyevent-based text entry SHG07 needed,
    # even though SHG10's own real end-to-end success (2026-09-11) used
    # input_text_direct() for 名前/APN. Not itself re-verified on real
    # SHG10 hardware yet — see docs/record.md, PENDING_REAL_DEVICE_DATA.md.
    assert apn["use_keyevent_text_entry"] is True


@pytest.mark.parametrize("filename", SCREEN_DRIVEN_MODEL_FILES)
def test_load_each_screen_driven_model_file(filename):
    """Both SHG10 (real device data) and SHG07 (inherited from SHG10,
    2026-09-14) use the same schema shape — this just confirms the file
    parses into that shape at all; the two model-specific tests below check
    the actual values."""
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
    # This one is real SHG07 data, not inherited — see docs/record.md,
    # 2026-09-14: the client's first real SHG07 dump/report found the
    # active IME interferes with plain `input text` entry for 名前/APN
    # there, unlike SHG10.
    assert apn["use_keyevent_text_entry"] is True


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
