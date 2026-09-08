"""Loads and exposes one config/models/*.yaml file as a ModelProfile."""

from __future__ import annotations

from pathlib import Path

import yaml

# "wizard_steps" (legacy, sequence-driven) and "wizard" (Stage B,
# screen-driven text matching — see docs/record.md "IMPLEMENTATION SPEC")
# are two different schemas for the same concept; a profile must have
# exactly one, not both required unconditionally.
_REQUIRED_TOP_LEVEL_FIELDS = (
    "model",
    "model_number",
    "manufacturer",
    "android_version",
    "wifi_settings",
    "apn_settings",
)
_REQUIRED_WIFI_FIELDS = ("toggle_resource_id", "network_list_resource_id")
# Only `menu_path` is enforced here. Stage A's apn_settings used literal
# per-field resource-ids (name_field_resource_id, etc); real SHG10 dumps
# showed those fields don't have dedicated resource-ids on that model — they
# share one generic id and are matched by label text instead (see
# apn_setup.py, PENDING_REAL_DEVICE_DATA.md). Since the two schemas legitimately
# differ per model, ModelProfile doesn't hard-require either shape beyond
# menu_path; apn_setup.py validates and raises its own clear error for
# whatever fields *it* actually needs and doesn't find.
_REQUIRED_APN_FIELDS = ("menu_path",)


class ModelProfileError(Exception):
    """Raised when a model YAML file is missing required fields or is
    otherwise malformed."""


class ModelProfile:
    """Loads and exposes one config/models/*.yaml file."""

    def __init__(self, data: dict):
        self._data = data

    @classmethod
    def load(cls, path: str) -> "ModelProfile":
        """Parse the YAML file at `path` into a ModelProfile instance.
        Raise ModelProfileError if required fields are missing."""
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict):
            raise ModelProfileError(f"{path}: expected a YAML mapping at top level")

        missing = [field for field in _REQUIRED_TOP_LEVEL_FIELDS if field not in data]
        if missing:
            raise ModelProfileError(f"{path}: missing required field(s) {missing}")

        wifi = data["wifi_settings"]
        missing_wifi = [f for f in _REQUIRED_WIFI_FIELDS if f not in wifi]
        if missing_wifi:
            raise ModelProfileError(
                f"{path}: wifi_settings missing required field(s) {missing_wifi}"
            )

        apn = data["apn_settings"]
        missing_apn = [f for f in _REQUIRED_APN_FIELDS if f not in apn]
        if missing_apn:
            raise ModelProfileError(
                f"{path}: apn_settings missing required field(s) {missing_apn}"
            )

        has_legacy_wizard = "wizard_steps" in data
        has_screen_driven_wizard = "wizard" in data
        if not has_legacy_wizard and not has_screen_driven_wizard:
            raise ModelProfileError(
                f"{path}: missing required field(s) ['wizard_steps' or 'wizard']"
            )

        if has_legacy_wizard:
            if not isinstance(data["wizard_steps"], list) or not data["wizard_steps"]:
                raise ModelProfileError(f"{path}: wizard_steps must be a non-empty list")
            for i, step in enumerate(data["wizard_steps"]):
                missing_step = [f for f in ("screen", "resource_id", "action") if f not in step]
                if missing_step:
                    raise ModelProfileError(
                        f"{path}: wizard_steps[{i}] missing required field(s) {missing_step}"
                    )

        if has_screen_driven_wizard:
            wizard = data["wizard"]
            screens = wizard.get("screens") if isinstance(wizard, dict) else None
            if not isinstance(screens, list) or not screens:
                raise ModelProfileError(f"{path}: wizard.screens must be a non-empty list")
            for i, screen in enumerate(screens):
                missing_screen = [
                    f for f in ("name", "identify_by_text", "action") if f not in screen
                ]
                if missing_screen:
                    raise ModelProfileError(
                        f"{path}: wizard.screens[{i}] missing required field(s) {missing_screen}"
                    )

        return cls(data)

    @property
    def model(self) -> str:
        return self._data["model"]

    @property
    def model_number(self) -> str:
        return self._data["model_number"]

    @property
    def manufacturer(self) -> str:
        return self._data["manufacturer"]

    @property
    def android_version(self) -> int:
        return self._data["android_version"]

    def has_screen_driven_wizard(self) -> bool:
        """True if this profile uses the Stage B screen-driven wizard schema
        (`wizard.screens`, matched by visible text — see
        docs/record.md) instead of Stage A's sequence-driven `wizard_steps`.
        """
        return "wizard" in self._data

    def wizard_steps(self) -> list[dict]:
        """Return the ordered list of setup-wizard steps for this model
        (legacy, sequence-driven schema). Only valid when
        has_screen_driven_wizard() is False."""
        return self._data["wizard_steps"]

    def wizard_screens(self) -> list[dict]:
        """Return the list of screen-driven wizard screen definitions (Stage
        B schema: identify by visible text, then act — see
        docs/record.md). Only valid when has_screen_driven_wizard() is
        True."""
        return self._data["wizard"]["screens"]

    def wifi_settings(self) -> dict:
        """Return the Wi-Fi-related resource-ids for this model."""
        return self._data["wifi_settings"]

    def apn_settings(self) -> dict:
        """Return the resource-ids and menu path needed for APN entry."""
        return self._data["apn_settings"]

    @classmethod
    def load_all(cls, models_dir: str) -> dict[str, "ModelProfile"]:
        """Load every *.yaml in models_dir, keyed by model_number (e.g. 'SOG08')."""
        profiles: dict[str, "ModelProfile"] = {}
        for yaml_path in sorted(Path(models_dir).glob("*.yaml")):
            profile = cls.load(str(yaml_path))
            profiles[profile.model_number] = profile
        return profiles
