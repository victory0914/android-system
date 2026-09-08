"""Configures a mobile APN entry by navigating Settings via UI Automator and
injecting text via ADB Keyboard (or, for numeric fields — see below —
Android's built-in `input text` command).

Stage B note (see docs/record.md, PENDING_REAL_DEVICE_DATA.md): real SHG10
captures showed the APN edit form does NOT expose a per-field resource-id —
every field row shares one generic id (`apn_settings['field_row_resource_id']`,
in practice "android:id/title") and is disambiguated only by its visible
Japanese label text (名前/APN/MCC/MNC/...). Tapping a row opens a small
EditTextPreference-style dialog; the dialog itself was never captured in a
real dump, so its EditText/confirm-button ids are best-guess standard AOSP
framework ids (TODO(real-device, best-guess-standard-id)), same convention
docs/record.md established for the wizard. (Indirect confirmation, 2026-09-08:
the *validation-error* dialog, which WAS captured, uses exactly
"android:id/button1" for its OK button — the same id already guessed for the
per-field dialog's confirm button, since both are standard AOSP AlertDialogs.)

APN save flow — confirmed on real SHG10 hardware, 2026-09-08 (see
docs/record.md): Save lives in the overflow "⋮" menu, not on the form
itself. Field validation is sequential and blocking — saving with any
required field empty/invalid shows a modal AlertDialog instead of returning
to the APN list, and does NOT save. MCC/MNC are mandatory, not optional
(an earlier note guessing they might be absent on this build was wrong —
they're simply further down the scrollable form than first assumed).

Models not yet given real APN data (the 3 untouched by Stage B — see
PENDING_REAL_DEVICE_DATA.md) still use Stage A's literal-resource-id shape
(name_field_resource_id / apn_field_resource_id / mcc_field_resource_id /
mnc_field_resource_id / save_button_resource_id); this module supports both,
branching on whether `field_row_resource_id` is present.

Never issues raw ADB shell taps directly for screen interaction — all screen
interaction goes through device/ui_automator.py.
"""

from __future__ import annotations

import logging
import re

from src.device.adb_client import AdbClientProtocol, AdbCommandError
from src.device.model_profile import ModelProfile
from src.device.ui_automator import (
    AmbiguousResourceIdError,
    dump_ui,
    find_by_content_desc,
    find_by_text,
    find_resource_id,
    get_node_text,
    inject_text,
    input_text_direct,
    navigate_menu_path,
    tap_by_content_desc,
    tap_by_text,
    tap_resource_id,
)

logger = logging.getLogger(__name__)

_REQUIRED_LEGACY_FIELDS = (
    "name_field_resource_id",
    "apn_field_resource_id",
    "save_button_resource_id",
)
_REQUIRED_LABELED_FIELDS = (
    "field_row_resource_id",
    "name_field_label",
    "apn_field_label",
    "mcc_field_label",
    "mnc_field_label",
)

# Standard AOSP AlertDialog ids — real capture, 2026-09-08 (validation dialog).
_DIALOG_MESSAGE_RESOURCE_ID = "android:id/message"

_MCC_PATTERN = re.compile(r"\d{3}")
_MNC_PATTERN = re.compile(r"\d{2,3}")


def _fill_legacy_field(client: AdbClientProtocol, resource_id: str, value: str) -> bool:
    """Stage A shape: the field itself has a dedicated resource-id — tap it
    to focus, then inject text. Returns False if the field wasn't found."""
    if not tap_resource_id(client, resource_id):
        return False
    return inject_text(client, value)


def _fill_labeled_field(
    client: AdbClientProtocol, apn: dict, label: str, value: str, *, numeric: bool = False
) -> bool:
    """Stage B shape: tap the row identified by (field_row_resource_id,
    text=label) to open its edit dialog, then type into the dialog's
    EditText and confirm. The dialog's own ids are best-guess standard
    framework ids (never captured directly) — if they're wrong,
    tap_resource_id() simply returns False rather than mistapping, and this
    function surfaces that as a failure rather than pretending it worked.

    `numeric=True` uses input_text_direct() (Android's built-in `input
    text`) instead of inject_text() (ADB Keyboard) — confirmed necessary on
    real hardware for MCC/MNC: the device's default IME is Japanese kana
    mode, and the on-screen keyboard can't reach digits without a mode
    switch UI automation has no reliable way to trigger.
    """
    row_resource_id = apn["field_row_resource_id"]
    if not tap_resource_id(client, row_resource_id, text=label):
        return False

    edit_field = apn.get("dialog_edit_field_resource_id")
    if edit_field and not tap_resource_id(client, edit_field):
        logger.warning(
            "apn field %r: dialog edit-field %r (best-guess id) not found; "
            "attempting text entry anyway in case it's already focused",
            label, edit_field,
        )

    entry_fn = input_text_direct if numeric else inject_text
    if not entry_fn(client, value):
        return False

    confirm_button = apn.get("dialog_confirm_button_resource_id")
    if confirm_button and not tap_resource_id(client, confirm_button):
        logger.warning(
            "apn field %r: dialog confirm button %r (best-guess id) not "
            "found — value may not have been saved into the field",
            label, confirm_button,
        )
    return True


def _step_target_present(ui_xml: str, step) -> bool:
    """Read-only check (no tap) for whether a single navigate_menu_path()
    step's target is visible in an already-taken dump."""
    if isinstance(step, str):
        step_type, value = "text", step
    else:
        step_type, value = step.get("type", "text"), step["value"]
    try:
        if step_type == "text":
            return find_by_text(ui_xml, value) is not None
        if step_type == "resource_id":
            return find_resource_id(ui_xml, value) is not None
        if step_type == "content_desc":
            return find_by_content_desc(ui_xml, value) is not None
    except AmbiguousResourceIdError:
        return True  # present, just ambiguous — good enough as a landing signal
    return False


def _navigate_apn_menu(client: AdbClientProtocol, apn: dict) -> bool:
    """Reach the APN entry screen via profile.apn_settings()['menu_path'].

    A real client-PC run showed the leading text steps of menu_path (e.g.
    tapping "設定") fail whenever the device isn't already on a screen where
    that text is visible — e.g. reached via --skip-wizard testing rather
    than a fresh wizard walkthrough. SHG10's confirmed path (and plausibly
    other models following the same "APN lives under Wi-Fi settings"
    pattern) reaches the same combined Wi-Fi/mobile-network screen that
    wifi_setup.py's android.settings.WIFI_SETTINGS intent goes to directly,
    before continuing with APN-specific steps (an icon, then a menu item).

    So: try that same intent, then do a **read-only** check (dump + find,
    no tap) of whether it landed somewhere the first non-text menu_path
    step is already reachable. Only then commit to skipping the leading
    text steps — never tap partway down one path and fall back to another,
    which could leave the UI in a state neither path recovers from
    correctly. Falls back to the full menu_path from the start otherwise —
    exactly Stage A's original behavior, zero regression risk if the
    intent doesn't help.
    """
    menu_path = apn["menu_path"]

    leading_text_steps = 0
    for step in menu_path:
        step_type = "text" if isinstance(step, str) else step.get("type", "text")
        if step_type != "text":
            break
        leading_text_steps += 1
    remaining_steps = menu_path[leading_text_steps:]

    if remaining_steps and leading_text_steps > 0:
        try:
            client.shell("am start -a android.settings.WIFI_SETTINGS")
        except AdbCommandError as exc:
            logger.info("am start WIFI_SETTINGS intent failed: %s", exc)
        else:
            ui_xml = dump_ui(client)
            if _step_target_present(ui_xml, remaining_steps[0]):
                logger.info(
                    "apn menu: WIFI_SETTINGS intent landed correctly, "
                    "skipping %d leading text step(s) of menu_path",
                    leading_text_steps,
                )
                return navigate_menu_path(client, remaining_steps)
            logger.info(
                "apn menu: WIFI_SETTINGS intent didn't land where the next "
                "menu_path step is reachable; falling back to the full path"
            )

    return navigate_menu_path(client, menu_path)


def _save_apn(client: AdbClientProtocol, apn: dict) -> bool:
    """Save the APN entry. Two shapes supported:

    - Stage B (SHG10, real device, confirmed 2026-09-08): Save lives in the
      overflow "⋮" menu — tap it (by content-desc; it has no resource-id,
      confirmed twice across separate captures), then tap "保存" inside it
      (shares android:id/title with the menu's other item, "キャンセル" —
      disambiguated by text, same pattern as everywhere else on this
      screen). Field validation is sequential and blocking: if a required
      field was empty/invalid, a modal AlertDialog appears instead of the
      APN list screen. Detected here by checking for android:id/message;
      if present, its real text is logged and this fails loudly rather
      than tapping OK and retrying blindly — a silent failure here would
      leave the device with no APN configured and no error surfaced.

    - Legacy (3 untouched models): a single literal save button.
    """
    overflow_content_desc = apn.get("overflow_menu_content_desc")

    if overflow_content_desc:
        if not tap_by_content_desc(client, overflow_content_desc):
            logger.error(
                "apn overflow menu (content-desc %r) not found", overflow_content_desc
            )
            return False

        save_label = apn.get("save_menu_item_text", "保存")
        if not tap_by_text(client, save_label):
            logger.error(
                "apn save menu item (text %r) not found in overflow menu", save_label
            )
            return False

        ui_xml = dump_ui(client)
        message = get_node_text(ui_xml, _DIALOG_MESSAGE_RESOURCE_ID)
        if message is not None:
            logger.error(
                "apn save blocked by validation dialog: %r — a required "
                "field was missing or invalid. Not tapping OK and retrying "
                "blindly (see docs/record.md, 'VALIDATION IS SEQUENTIAL AND "
                "BLOCKING' — a silent failure here would leave the device "
                "with no APN configured and no error surfaced).",
                message,
            )
            return False

        return True

    save_button = apn.get("save_button_resource_id")
    if not save_button:
        logger.error(
            "apn_settings has neither overflow_menu_content_desc nor "
            "save_button_resource_id configured — configure_apn() cannot "
            "complete. See PENDING_REAL_DEVICE_DATA.md."
        )
        return False
    if not tap_resource_id(client, save_button):
        logger.error("apn save button %r not found", save_button)
        return False
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
    on success.

    mcc/mnc are required, not optional (confirmed on real SHG10 hardware,
    2026-09-08) — the device itself validates them (MCC exactly 3 digits,
    MNC 2 or 3) and refuses to save otherwise, so this checks the same
    constraint up front rather than discovering it after a slow UI
    round-trip.
    """
    if not _MCC_PATTERN.fullmatch(mcc):
        logger.error("apn mcc %r is not exactly 3 digits — device will reject this", mcc)
        return False
    if not _MNC_PATTERN.fullmatch(mnc):
        logger.error("apn mnc %r is not 2 or 3 digits — device will reject this", mnc)
        return False

    apn = profile.apn_settings()

    if not _navigate_apn_menu(client, apn):
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
        missing = [f for f in _REQUIRED_LABELED_FIELDS if not apn.get(f)]
        if missing:
            logger.error("apn_settings missing required field(s) %s", missing)
            return False

        # Fill ALL fields before ever tapping save — confirmed on real
        # hardware that validation is sequential and blocking, so a partial
        # save attempt just wastes a round-trip on a guaranteed failure.
        fields = [
            (apn["name_field_label"], apn_name, False),
            (apn["apn_field_label"], apn_name, False),
            (apn["mcc_field_label"], mcc, True),
            (apn["mnc_field_label"], mnc, True),
        ]
        for label, value, numeric in fields:
            if not _fill_labeled_field(client, apn, label, value, numeric=numeric):
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

    if not _save_apn(client, apn):
        return False

    logger.info("apn %r configured successfully", apn_name)
    return True
