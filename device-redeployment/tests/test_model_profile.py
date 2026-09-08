"""Tests for src/device/model_profile.py against the four real model YAML
files shipped in config/models/."""

from pathlib import Path

import pytest

from src.device.model_profile import ModelProfile, ModelProfileError

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "config" / "models"

# The 3 models Stage B did not touch still use Stage A's legacy,
# resource-id-based schema throughout. SHG10 was updated with real device
# data (see docs/record.md) and uses the newer screen-driven wizard schema
# plus label-based APN fields — validated separately below.
LEGACY_MODEL_FILES = [
    "sony_xperia_ace3.yaml",
    "sony_xperia_10iv.yaml",
    "sharp_aquos_sense6s.yaml",
]
MODEL_FILES = LEGACY_MODEL_FILES + ["sharp_aquos_sense7.yaml"]

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
    assert apn["save_button_resource_id"] is None


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
