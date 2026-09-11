"""Configures a mobile APN entry by navigating Settings via UI Automator and
injecting text. Labeled-shape models (SHG10) use Android's built-in `input
text` command (input_text_direct()) for every field — confirmed necessary
on real hardware, see below. Legacy-shape models (the 3 untouched by Stage
B) still use the ADB Keyboard broadcast (inject_text()).

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
    get_node_text,
    inject_text,
    input_text_direct,
    navigate_menu_path,
    scroll_down,
    tap_by_content_desc,
    tap_by_text,
    tap_left_of_content_desc,
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
    client: AdbClientProtocol, apn: dict, label: str, value: str
) -> bool:
    """Stage B shape: tap the row identified by (field_row_resource_id,
    text=label) to open its edit dialog, then type into the dialog's
    EditText and confirm. The dialog's own ids are best-guess standard
    framework ids (never captured directly) — if they're wrong,
    tap_resource_id() simply returns False rather than mistapping, and this
    function surfaces that as a failure rather than pretending it worked.

    Both the edit-field tap and the confirm-button tap are treated as HARD
    failures if the (best-guess) id isn't found — NOT soft warnings that
    let execution continue (2026-09-11 fix; an earlier version only warned
    and returned True, on the theory the EditText might already be
    auto-focused). Real-device testing showed why that was dangerous: if
    the confirm button silently fails to be found, its dialog is left open,
    and every subsequent tap (the next field's row, the overflow menu, the
    save item) lands on — or is swallowed by — that still-open modal
    instead of what it was aimed at, typing later fields' values into the
    same stuck EditText and ultimately failing at the *save* step with a
    confusing "menu item not found" error that looks like a save-flow bug
    but actually originates here, several steps earlier. Failing loudly at
    the field that actually didn't commit is far more diagnosable — see
    docs/record.md, 2026-09-11.

    Uses input_text_direct() (Android's built-in `input text`), not
    inject_text() (ADB Keyboard broadcast) — confirmed necessary on real
    hardware, and not just for MCC/MNC as first thought: MCC/MNC needed it
    because the default IME (Japanese kana mode) can't reach digits without
    a mode switch, but a *second* real run (2026-09-08, Wi-Fi password
    entry — same device, same inject_text() call) showed the ADB Keyboard
    broadcast does nothing at all here, consistent with that app not
    actually being installed/active. So this now applies to every field on
    this device, not just numeric ones.
    """
    row_resource_id = apn["field_row_resource_id"]
    if not tap_resource_id(client, row_resource_id, text=label):
        # Real hardware confirmed (2026-09-08): MCC/MNC are below the fold
        # in this scrollable form — a row not yet scrolled into view can be
        # genuinely absent from the dump, not just hard to find. Scroll
        # once and retry before giving up, same pattern as the wizard's
        # scroll_then_tap_by_text.
        scroll_down(client)
        if not tap_resource_id(client, row_resource_id, text=label):
            return False

    edit_field = apn.get("dialog_edit_field_resource_id")
    if edit_field and not tap_resource_id(client, edit_field):
        logger.error(
            "apn field %r: dialog edit-field %r (best-guess id) not found "
            "— refusing to type blindly into whatever currently has focus "
            "(see PENDING_REAL_DEVICE_DATA.md: this dialog has never been "
            "captured in a real dump, so this id is unconfirmed)",
            label, edit_field,
        )
        return False

    if not input_text_direct(client, value):
        return False

    confirm_button = apn.get("dialog_confirm_button_resource_id")
    if confirm_button and not tap_resource_id(client, confirm_button):
        logger.error(
            "apn field %r: dialog confirm button %r (best-guess id) not "
            "found — the value was typed but NOT committed, and the dialog "
            "is likely still open. Failing here rather than continuing: "
            "every later tap (next field, save) would otherwise land on "
            "this stuck dialog instead of its intended target. See "
            "PENDING_REAL_DEVICE_DATA.md — this id has never been "
            "confirmed against a real dump of the per-field dialog.",
            label, confirm_button,
        )
        return False
    return True


_APN_LIST_SCREEN_TITLE_CONTENT_DESC = "アクセスポイント名"
_APN_LIST_SCREEN_TITLE_CONTENT_DESC_ALT = "APN"


def _looks_like_apn_list_screen(ui_xml: str) -> bool:
    """Best-effort check for the APN list screen. Two title variants
    confirmed real, both accepted here — and BOTH render via `content-desc`
    on the toolbar, never as a `text` node (same pattern already confirmed
    for the edit form's "アクセスポイントの編集"):

    - SHARP's own screen (reached via the fallback menu_path — manual
      navigation): `content-desc` "アクセスポイント名" (see
      tests/fixtures/apn_entry_*_SHG10.xml).

    - The stock/AOSP screen reached via `android.settings.APN_SETTINGS`
      (the primary path): `content-desc` "APN" instead — confirmed by a
      real dump, tests/fixtures/apn_restricted_SHG10.xml (2026-09-11,
      resource-id com.android.settings:id/collapsing_toolbar). An earlier
      version of this check looked for "APN" as plain `text`, based on a
      misreading of a screenshot before this dump existed — that never
      would have matched this real screen at all. This screen also shows a
      warning, 「このユーザーはアクセスポイント名設定を利用できません」
      ("this user cannot use APN name settings") — initially read as a
      hard access restriction, but the client confirmed the "+" button on
      this exact screen still works with a normal tap; that message
      doesn't block basic add/edit. See docs/record.md.
    """
    try:
        if find_by_content_desc(ui_xml, _APN_LIST_SCREEN_TITLE_CONTENT_DESC) is not None:
            return True
    except AmbiguousResourceIdError:
        return True
    except Exception:
        pass

    try:
        return find_by_content_desc(ui_xml, _APN_LIST_SCREEN_TITLE_CONTENT_DESC_ALT) is not None
    except AmbiguousResourceIdError:
        return True
    except Exception:
        return False


def _navigate_apn_menu(client: AdbClientProtocol, apn: dict) -> bool:
    """Reach the APN entry (list) screen.

    Real hand-testing on SHG10 (2026-09-08/09) confirmed
    `adb shell am start -a android.settings.APN_SETTINGS` reaches the APN
    list screen in a single step, bypassing the multi-tap Settings ->
    Network & internet -> Wi-Fi and mobile network -> gear icon path
    entirely. Tried first; falls back to `apn_settings['menu_path']`
    (Settings -> ... -> the gear icon; note the destination screen's own
    title is not itself a tap target — see _looks_like_apn_list_screen)
    only if the intent isn't available or doesn't land correctly.
    """
    try:
        client.shell("am start -a android.settings.APN_SETTINGS")
    except AdbCommandError as exc:
        logger.info("am start APN_SETTINGS intent failed: %s", exc)
    else:
        ui_xml = dump_ui(client)
        if _looks_like_apn_list_screen(ui_xml):
            logger.info("reached APN list via android.settings.APN_SETTINGS intent")
            return True
        logger.info(
            "APN_SETTINGS intent didn't land on a recognizable APN list "
            "screen; falling back to menu_path navigation"
        )

    menu_path = apn.get("menu_path")
    if not menu_path:
        return False
    return navigate_menu_path(client, menu_path)


def _save_apn(client: AdbClientProtocol, apn: dict, apn_name: str) -> bool:
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

      After a save with no validation dialog, makes one best-effort,
      *soft* positive check: real hand-testing confirmed a successful save
      shows the new entry back on the APN list with `apn_name` as its
      first line. Only logged (info if found, warning if not) — never
      turns a save the validation check already accepted into a failure,
      since e.g. list scroll position or display truncation could make
      this check miss a genuinely successful save.

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

        try:
            entry_visible = find_by_text(ui_xml, apn_name) is not None
        except Exception:
            entry_visible = False
        if entry_visible:
            logger.info("apn: new entry %r confirmed visible on the APN list", apn_name)
        else:
            logger.warning(
                "apn: save reported no validation error, but %r wasn't "
                "spotted back on the APN list (soft check only — not "
                "treated as a failure; could be scroll position or list "
                "truncation)",
                apn_name,
            )

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
    type the APN name and value fields directly (input_text_direct() for
    labeled-shape/SHG10, inject_text() for legacy-shape models) — never
    simulate individual keystrokes for this. Tap save. Return True on
    success.

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
    add_button_content_desc = apn.get("add_button_content_desc")
    if add_button:
        if not tap_resource_id(client, add_button):
            logger.warning(
                "apn add-new button %r not found; assuming a blank entry is "
                "already open (e.g. this screen has no existing APNs yet)",
                add_button,
            )
    elif add_button_content_desc:
        # Real dump (tests/fixtures/apn_restricted_SHG10.xml, 2026-09-11)
        # confirmed the "+" button is a genuine, unambiguous
        # content-desc "新しい APN" ("New APN") — no estimate needed once
        # this is set; prefer it over the position-estimate fallback below.
        if not tap_by_content_desc(client, add_button_content_desc):
            logger.warning(
                "apn add-new button (content-desc %r) not found; assuming "
                "a blank entry is already open (e.g. this screen has no "
                "existing APNs yet)",
                add_button_content_desc,
            )
    elif apn.get("overflow_menu_content_desc"):
        # Fallback for models/screens where "+" has no identifier of its
        # own captured yet (not SHG10 anymore — see add_button_content_desc
        # above). Real screenshot (2026-09-11) confirmed it sits
        # immediately left of the "⋮" overflow menu, whose content-desc IS
        # confirmed, so this taps an ESTIMATED position derived from that
        # icon's own real bounds rather than doing nothing. See
        # tap_left_of_content_desc()'s docstring — it can only confirm the
        # overflow icon was found, not that the tap actually landed on
        # "+"; a wrong estimate here fails loudly a few lines later when
        # the expected field rows aren't found.
        if not tap_left_of_content_desc(client, apn["overflow_menu_content_desc"]):
            logger.warning(
                "apn add-new button: could not even find the overflow menu "
                "(content-desc %r) to estimate its position from",
                apn["overflow_menu_content_desc"],
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
            (apn["name_field_label"], apn_name),
            (apn["apn_field_label"], apn_name),
            (apn["mcc_field_label"], mcc),
            (apn["mnc_field_label"], mnc),
        ]
        for label, value in fields:
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

    if not _save_apn(client, apn, apn_name):
        return False

    logger.info("apn %r configured successfully", apn_name)
    return True
