"""Configures a mobile APN entry by navigating Settings via UI Automator and
injecting text via ADB Keyboard.

Stage B note (see docs/record.md, PENDING_REAL_DEVICE_DATA.md): real SHG10
captures showed the APN edit form does NOT expose a per-field resource-id —
every field row shares one generic id (`apn_settings['field_row_resource_id']`,
in practice "android:id/title") and is disambiguated only by its visible
Japanese label text (名前/APN/MCC/MNC/...). Tapping a row opens a small
EditTextPreference-style dialog; the dialog itself was never captured in a
real dump, so its EditText/confirm-button ids are best-guess standard AOSP
framework ids (TODO(real-device, best-guess-standard-id)), same convention
docs/record.md established for the wizard.

Models not yet given real APN data (the 3 untouched by Stage B — see
PENDING_REAL_DEVICE_DATA.md) still use Stage A's literal-resource-id shape
(name_field_resource_id / apn_field_resource_id / mcc_field_resource_id /
mnc_field_resource_id); this module supports both, branching on whether
`field_row_resource_id` is present.

Never issues raw ADB shell taps directly for screen interaction — all screen
interaction goes through device/ui_automator.py.
"""

from __future__ import annotations

import logging

from src.device.adb_client import AdbClientProtocol
from src.device.model_profile import ModelProfile
from src.device.ui_automator import inject_text, navigate_menu_path, tap_resource_id

logger = logging.getLogger(__name__)

_REQUIRED_LEGACY_FIELDS = (
    "name_field_resource_id",
    "apn_field_resource_id",
    "save_button_resource_id",
)


def _fill_legacy_field(client: AdbClientProtocol, resource_id: str, value: str) -> bool:
    """Stage A shape: the field itself has a dedicated resource-id — tap it
    to focus, then inject text. Returns False if the field wasn't found."""
    if not tap_resource_id(client, resource_id):
        return False
    return inject_text(client, value)


def _fill_labeled_field(
    client: AdbClientProtocol, apn: dict, label: str, value: str
) -> bool:
    """Stage B shape: tap the row identified by (field_row_resource_id,
    text=label) to open its edit dialog, then type into the dialog's
    EditText and confirm. The dialog's own ids are best-guess standard
    framework ids (never captured directly) — if they're wrong,
    tap_resource_id() simply returns False rather than mistapping, and this
    function surfaces that as a failure rather than pretending it worked."""
    row_resource_id = apn["field_row_resource_id"]
    if not tap_resource_id(client, row_resource_id, text=label):
        return False

    edit_field = apn.get("dialog_edit_field_resource_id")
    if edit_field and not tap_resource_id(client, edit_field):
        logger.warning(
            "apn field %r: dialog edit-field %r (best-guess id) not found; "
            "attempting inject_text() anyway in case it's already focused",
            label, edit_field,
        )
    if not inject_text(client, value):
        return False

    confirm_button = apn.get("dialog_confirm_button_resource_id")
    if confirm_button and not tap_resource_id(client, confirm_button):
        logger.warning(
            "apn field %r: dialog confirm button %r (best-guess id, "
            "unverified) not found — value may not have been saved into "
            "the field",
            label, confirm_button,
        )
    return True


def configure_apn(
    client: AdbClientProtocol,
    profile: ModelProfile,
    apn_name: str,
    mcc: str,
    mnc: str,
) -> bool:
    """Navigate profile.apn_settings()['menu_path'] via UI Automator, then
    use inject_text() (ADB Keyboard) to enter the APN name and value fields
    — never simulate individual keystrokes for this. Tap save. Return True
    on success."""
    apn = profile.apn_settings()

    if not navigate_menu_path(client, apn["menu_path"]):
        logger.error("apn menu navigation failed")
        return False

    add_button = apn.get("add_button_resource_id")
    if add_button:
        if not tap_resource_id(client, add_button):
            logger.warning(
                "apn add-new button %r not found; assuming a blank entry is "
                "already open (e.g. this screen has no existing APNs yet)",
                add_button,
            )
    else:
        logger.debug(
            "apn_settings.add_button_resource_id not configured for this "
            "model — see PENDING_REAL_DEVICE_DATA.md"
        )

    uses_labeled_fields = "field_row_resource_id" in apn

    if uses_labeled_fields:
        fields = [(apn.get("name_field_label"), apn_name), (apn.get("apn_field_label"), apn_name)]
        if apn.get("mcc_field_label"):
            fields.append((apn["mcc_field_label"], mcc))
        if apn.get("mnc_field_label"):
            fields.append((apn["mnc_field_label"], mnc))

        for label, value in fields:
            if label is None:
                continue
            if not _fill_labeled_field(client, apn, label, value):
                logger.error("apn field labeled %r not found/could not be filled", label)
                return False
    else:
        missing = [f for f in _REQUIRED_LEGACY_FIELDS if f not in apn]
        if missing:
            logger.error("apn_settings missing required field(s) %s", missing)
            return False

        if not _fill_legacy_field(client, apn["name_field_resource_id"], apn_name):
            logger.error("apn name field %r not found", apn["name_field_resource_id"])
            return False
        if not _fill_legacy_field(client, apn["apn_field_resource_id"], apn_name):
            logger.error("apn value field %r not found", apn["apn_field_resource_id"])
            return False

        mcc_field = apn.get("mcc_field_resource_id")
        if mcc_field:
            _fill_legacy_field(client, mcc_field, mcc)
        mnc_field = apn.get("mnc_field_resource_id")
        if mnc_field:
            _fill_legacy_field(client, mnc_field, mnc)

    save_button = apn.get("save_button_resource_id")
    if not save_button:
        logger.error(
            "apn_settings.save_button_resource_id is unresolved for this "
            "model — no Save affordance was found in the captured dumps, "
            "so configure_apn() cannot complete. See "
            "PENDING_REAL_DEVICE_DATA.md ('Where is the Save action?')."
        )
        return False

    if not tap_resource_id(client, save_button):
        logger.error("apn save button %r not found", save_button)
        return False

    logger.info("apn %r configured successfully", apn_name)
    return True
