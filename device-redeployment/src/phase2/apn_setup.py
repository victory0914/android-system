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
per-field AlertDialog; its EditText/confirm-button ids were first only
best-guess standard AOSP framework ids (inferred from the *validation-error*
dialog, which shares the same "android:id/button1" OK id), then directly
RESOLVED by a real dump of the dialog itself while open
(tests/fixtures/apn_accesshost_okbtn_SHG10.xml, 2026-09-11) — the guess was
exactly right: EditText at "android:id/edit", "OK" at "android:id/button1",
"キャンセル" at "android:id/button2" (the dialog's title even renders via
the standard "com.android.settings:id/alertTitle", confirming it's a plain
AOSP AlertDialog, not a custom layout).

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
import time

from src.device.adb_client import AdbClientProtocol, AdbCommandError
from src.device.model_profile import ModelProfile
from src.device.ui_automator import (
    AmbiguousResourceIdError,
    dump_ui,
    find_by_content_desc,
    find_by_text,
    get_current_ime,
    get_node_text,
    inject_text,
    input_ascii_direct,
    input_digits_direct,
    input_text_direct,
    navigate_menu_path,
    scroll_down,
    tap_at_coordinates,
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

# Real hardware (2026-09-11): a successful save can take a moment for the
# APN list's RecyclerView to actually reflect the new entry — the dump
# taken immediately after tapping 保存 showed the pre-save (empty) list
# even though the save had genuinely already succeeded (confirmed by the
# client manually re-opening the same screen moments later and finding the
# entry present and selected). One retry after this delay avoids reporting
# a false-negative warning for what is, in practice, just a slow list
# refresh — not a real save failure.
_POST_SAVE_RECHECK_DELAY_SECONDS = 2.0

# Kept as cheap, harmless insurance (originally a standalone hypothesis,
# 2026-09-17, for why a live SOG07 run kept committing full-width MCC/MNC
# digits) even though the client subsequently identified the REAL root
# cause below (_KEYBOARD_TOGGLE_MAX_ATTEMPTS) — a short pause before each
# round of toggle taps, giving the on-screen keyboard's own animations
# time to settle, costs nothing and might still help on some device.
_KEYBOARD_TOGGLE_TAP_DELAY_SECONDS = 0.5

# Real root cause identified by the client (2026-09-17, SOG07), directly
# from watching a live run: the on-screen keyboard's mode-toggle key does
# NOT reset to a known state for each new field's dialog — it carries over
# from wherever the PREVIOUS field's typing left it. "Always tap exactly
# twice" (the SHG07 recipe) only works for the first field opened in a
# fresh dialog session (starts in kana mode, 2 taps reaches alphanumeric);
# for every field after that, 2 taps from an unknown carried-over state
# can land anywhere in the toggle's cycle — the client's own real
# observation: 名前 and APN come out correct, but MCC (the third field
# typed into) then comes out full-width, consistent with the toggle
# cycling past the correct mode rather than landing on it.
#
# There is no way to directly READ the keyboard's current mode — it is
# invisible to `uiautomator dump` (see tap_at_coordinates()'s docstring),
# and get_current_ime() only reports the active IME package, not its
# subtype/mode. So instead of trying to track or predict the toggle's
# state machine, _fill_labeled_field() PROBES it empirically: type, read
# the field back (the verification that already existed), and if it
# doesn't match, clear the field and advance the toggle by one more
# single tap before retrying — up to this many total attempts (the first
# attempt's initial 2 taps, then up to N-1 single-tap corrections) before
# giving up and failing loudly through the existing cancel/navigate-up
# cleanup path. Bounded rather than unlimited so a genuinely broken field
# (wrong id, real device problem) still fails instead of looping forever.
_KEYBOARD_TOGGLE_MAX_ATTEMPTS = 4


def _cleanup_mismatched_field_dialog(client: AdbClientProtocol, apn: dict, label: str) -> None:
    """Best-effort: tap Cancel, then the toolbar's navigate-up icon, to
    back out of a field dialog cleanly after a hard field-fill failure —
    real, two-part finding (2026-09-15, SHG07; see docs/record.md).
    Cancelling the dialog alone isn't enough: it leaves the device sitting
    on the "アクセスポイントの編集" edit *form* for the in-progress new
    entry (never saved, never discarded), not back on the APN *list* —
    the next run's android.settings.APN_SETTINGS intent then lands on
    that leftover form instead of the list, failing navigation on every
    attempt. Both steps are best-effort and only ever logged on failure,
    never raised — this must not mask whatever real error triggered the
    cleanup in the first place."""
    cancel_button = apn.get("dialog_cancel_button_resource_id")
    if cancel_button and not tap_resource_id(client, cancel_button):
        logger.warning(
            "apn field %r: also could not tap the cancel button %r to "
            "back out of the mismatched dialog — the device may be left "
            "showing it; check before the next run.",
            label, cancel_button,
        )
    navigate_up_content_desc = apn.get("navigate_up_content_desc")
    if navigate_up_content_desc and not tap_by_content_desc(client, navigate_up_content_desc):
        logger.warning(
            "apn field %r: also could not tap the navigate-up icon "
            "(content-desc %r) to exit the abandoned new-entry form — "
            "the device may be left showing it; check before the next run.",
            label, navigate_up_content_desc,
        )


def _fill_legacy_field(client: AdbClientProtocol, resource_id: str, value: str) -> bool:
    """Stage A shape: the field itself has a dedicated resource-id — tap it
    to focus, then inject text. Returns False if the field wasn't found."""
    if not tap_resource_id(client, resource_id):
        return False
    return inject_text(client, value)


def _fill_labeled_field(
    client: AdbClientProtocol, apn: dict, label: str, value: str, *, numeric_only: bool = False
) -> bool:
    """Stage B shape: tap the row identified by (field_row_resource_id,
    text=label) to open its edit dialog, then type into the dialog's
    EditText and confirm. The dialog's own ids are RESOLVED, real values
    (tests/fixtures/apn_accesshost_okbtn_SHG10.xml, 2026-09-11 — a dump of
    the dialog itself while open) — if a tap still doesn't land,
    tap_resource_id() returns False rather than mistapping, and this
    function surfaces that as a failure rather than pretending it worked.

    `numeric_only=True` (used for MCC/MNC — see configure_apn()) types via
    input_digits_direct() (per-digit KEYCODE_N keyevents) instead of
    input_text_direct() (`input text`). Real-device finding (client report,
    2026-09-11): `input text` commits MCC/MNC as FULL-WIDTH digits
    (e.g. "４４０") on this device instead of half-width/ASCII ("440") —
    the on-device validation almost certainly rejects full-width digits as
    not matching "N digits", which would explain a real run getting all
    the way through typing every field (this doesn't fail — the dialog
    closes normally) yet the entry never actually saving. See
    input_digits_direct()'s docstring for why keyevents avoid this.

    Both the edit-field tap and the confirm-button tap are treated as HARD
    failures if the id isn't found — NOT soft warnings that let execution
    continue (2026-09-11 fix, made before the ids above were confirmed; an
    earlier version only warned and returned True, on the theory the
    EditText might already be auto-focused). Real-device testing showed why
    that was dangerous: if the confirm button silently fails to be found,
    its dialog is left open, and every subsequent tap (the next field's
    row, the overflow menu, the save item) lands on — or is swallowed by —
    that still-open modal instead of what it was aimed at, typing later
    fields' values into the same stuck EditText and ultimately failing at
    the *save* step with a confusing "menu item not found" error that looks
    like a save-flow bug but actually originates here, several steps
    earlier. Failing loudly at the field that actually didn't commit is far
    more diagnosable — see docs/record.md, 2026-09-11. Kept even now that
    the ids are confirmed correct: still the right behavior if a future
    build/OS update ever changes them.

    Uses input_text_direct() (Android's built-in `input text`) by default,
    not inject_text() (ADB Keyboard broadcast) — confirmed necessary on
    real hardware, and not just for MCC/MNC as first thought: MCC/MNC
    needed it because the default IME (Japanese kana mode) can't reach
    digits without a mode switch, but a *second* real run (2026-09-08,
    Wi-Fi password entry — same SHG10 device, same inject_text() call)
    showed the ADB Keyboard broadcast does nothing at all there, consistent
    with that app not actually being installed/active. So this applies to
    every field on SHG10, not just numeric ones.

    `apn_settings.use_keyevent_text_entry=True` (SHG07, 2026-09-14) skips
    input_text_direct() for non-numeric fields too, using
    input_ascii_direct() instead — see that function's docstring. SHG10
    does NOT set this flag; input_text_direct() is already proven working
    there for 名前/APN specifically (real end-to-end success, 2026-09-11),
    so this stays opt-in per model rather than applying everywhere.

    `apn_settings.keyboard_mode_toggle_tap_numeric` (SOG07/SOG08,
    2026-09-17) is a SEPARATE, independently-confirmed coordinate used
    only for numeric_only fields (MCC/MNC), falling back to
    `keyboard_mode_toggle_tap` when unset. Real finding: unlike SHG07,
    where one coordinate happened to work for every field, MCC/MNC on
    Sony hardware open a genuinely different numeric-only keypad layout
    whose toggle key sits at a different position — reusing the
    text-keyboard coordinate there is a near-miss at best (silently
    lands on the wrong key) and a mistap at worst.

    `apn_settings.use_text_entry_for_numeric` (SOG07, 2026-09-17) makes
    MCC/MNC use input_text_direct() instead of input_digits_direct().
    Real finding: even with the correct toggle coordinate confirmed and
    applied, a live run kept committing full-width digits — the toggle
    only actually took effect for input_text_direct()'s mechanism on this
    keypad, not input_digits_direct()'s per-keyevent one. Device-specific
    like every other text-entry flag here; SHG10/SHG07 keep the original
    keyevent mechanism, which is proven working for them.

    Whenever a toggle coordinate AND edit_field are both configured
    (every field this applies to, numeric or not), only the value's own
    FIRST character is used to probe the toggle's self-correction loop —
    not the whole value — and the rest is typed once, for real, only
    after that probe is confirmed correct (client feedback, 2026-09-17:
    retyping the whole value on every correction attempt was needlessly
    slow, then extended from numeric-only to every field after the same
    full-value retyping was observed on 名前/APN on real SOG07 hardware).
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
            "apn field %r: dialog edit-field %r not found (real, confirmed "
            "id — see tests/fixtures/apn_accesshost_okbtn_SHG10.xml; a "
            "miss here means something about this specific dialog's state "
            "was unexpected, not a wrong id) — refusing to type blindly "
            "into whatever currently has focus",
            label, edit_field,
        )
        return False

    # Real, directly-confirmed fix (client, 2026-09-15, SHG07): the
    # on-screen keyboard's かな/英数 mode-toggle key — invisible to
    # uiautomator dump (see tap_at_coordinates()'s docstring) — must be
    # tapped before typing, or the active IME transforms the input
    # regardless of mechanism: input_text_direct()/input_ascii_direct()
    # both get letters converted to kana (see docs/record.md, 2026-09-15,
    # rounds 2 and 6), and input_digits_direct() gets digits converted to
    # full-width ("440" → "４４０") too when the keyboard is left in kana
    # mode.
    #
    # `apn_settings.keyboard_mode_toggle_tap_numeric` (SOG07/SOG08,
    # 2026-09-17) is a SEPARATE, independently-confirmed coordinate used
    # only for numeric_only fields (MCC/MNC), falling back to
    # `keyboard_mode_toggle_tap` when unset. Real finding: unlike SHG07,
    # where one coordinate happened to work for every field, MCC/MNC on
    # Sony hardware open a genuinely different numeric-only keypad layout
    # whose toggle key sits at a different position — reusing the
    # text-keyboard coordinate there is a near-miss at best (silently
    # lands on the wrong key) and a mistap at worst.
    if numeric_only:
        toggle_coords = apn.get("keyboard_mode_toggle_tap_numeric") or apn.get(
            "keyboard_mode_toggle_tap"
        )
    else:
        toggle_coords = apn.get("keyboard_mode_toggle_tap")

    def _type_fn(text: str):
        """Returns a zero-arg callable that types `text` via whatever
        mechanism this model/field wants — a closure factory rather than
        one fixed function, since the probe-based numeric path below
        needs to type first a single probe character, then (separately)
        the rest of the value, through the same mechanism."""
        def _do() -> bool:
            if numeric_only:
                # `apn_settings.use_text_entry_for_numeric` (SOG07,
                # 2026-09-17): even with the correct toggle coordinate, a
                # live run kept committing full-width digits — the toggle
                # only actually took effect for input_text_direct()'s
                # mechanism on this keypad, not input_digits_direct()'s
                # per-keyevent one. Mirror image of SHG10's original
                # finding (there, `input text` was the broken mechanism
                # and keyevents were the fix) — device-specific either
                # way, so opt-in.
                if apn.get("use_text_entry_for_numeric"):
                    return input_text_direct(client, text)
                return input_digits_direct(client, text)
            if apn.get("use_keyevent_text_entry"):
                # Real-device finding (client report, 2026-09-14, SHG07):
                # unlike SHG10, where input_text_direct() works fine for
                # 名前/APN, on this model the active Japanese IME affects
                # plain alphanumeric `input text` entry too — not just
                # digits. Per-character keyevents route around it the
                # same way numeric_only already does. See
                # input_ascii_direct()'s docstring for why this doesn't
                # instead try to detect-and-switch the device's IME.
                return input_ascii_direct(client, text)
            return input_text_direct(client, text)
        return _do

    def _toggle_and_type_with_retry(type_fn, expected: str) -> tuple[bool | None, str | None]:
        """Real root cause identified by the client (2026-09-17, SOG07):
        the toggle key's mode does NOT reset for each new field's
        dialog — it carries over from wherever the PREVIOUS field's
        typing left it. A single fixed "tap exactly twice" only works for
        the first field opened in a fresh dialog session; every field
        after that can start from an unpredictable carried-over state.
        See _KEYBOARD_TOGGLE_MAX_ATTEMPTS's module-level comment for the
        full reasoning and why this probes empirically (type + read back
        + correct) rather than trying to track the toggle's actual
        state.

        Calls type_fn(), reads the field back, and — if it doesn't match
        `expected` — clears it and advances the toggle by one more single
        tap before retrying, up to _KEYBOARD_TOGGLE_MAX_ATTEMPTS total
        attempts. Returns (True, actual) on a confirmed match,
        (False, actual) if the attempt budget is exhausted without one,
        or (None, None) if type_fn() itself reported a hard failure
        (caller should propagate that as an immediate False, no cleanup
        needed since nothing was typed).
        """
        actual = None
        max_attempts = _KEYBOARD_TOGGLE_MAX_ATTEMPTS if toggle_coords else 1
        for attempt in range(max_attempts):
            if toggle_coords:
                time.sleep(_KEYBOARD_TOGGLE_TAP_DELAY_SECONDS)
                x, y = toggle_coords
                if attempt == 0:
                    # The proven SHG07 starting recipe: a fresh dialog
                    # starts in kana mode and needs exactly two taps to
                    # reach the usable alphanumeric/half-width mode.
                    tap_at_coordinates(client, x, y)
                    tap_at_coordinates(client, x, y)
                else:
                    # A previous attempt's wrong value is still sitting
                    # in the field — clear it (one backspace per
                    # character; the field's own committed length, not
                    # len(expected), since a full-width mismatch isn't
                    # necessarily the same length) before retyping, then
                    # advance the toggle by one more single step and try
                    # again.
                    if actual:
                        for _ in range(len(actual)):
                            client.shell("input keyevent KEYCODE_DEL")
                    tap_at_coordinates(client, x, y)

            if not type_fn():
                return None, None

            if not edit_field:
                # Nothing to read back from — trust it, same as before
                # this retry loop existed (only legacy/unconfirmed-dialog
                # models reach this).
                return True, None

            # Read back what actually landed in the field BEFORE
            # confirming — real, concrete proof this matters (client
            # screenshot, 2026-09-15, SHG07): the active IME silently
            # transformed keyevent-typed "rakuten.jp" into "らくてん。" —
            # the field-row tap, the edit-field tap, the typing call, and
            # the confirm-button tap would all "succeed" with no error,
            # so nothing before this point could have caught it.
            ui_xml = dump_ui(client)
            actual = get_node_text(ui_xml, edit_field)
            if actual == expected:
                return True, actual
        return False, actual

    def _fail_mismatch(typed: str, actual: str | None, attempts: int) -> None:
        logger.error(
            "apn field %r: typed %r but the field now reads %r after %d "
            "toggle attempt(s) — the active input method appears to have "
            "transformed it every time (see docs/record.md, 2026-09-17). "
            "Refusing to confirm/save a value that doesn't match what was "
            "actually intended.",
            label, typed, actual, attempts,
        )
        # Real finding (2026-09-15): simply returning False here left this
        # dialog open on the device — see _cleanup_mismatched_field_dialog()'s
        # docstring for why both a Cancel tap and a navigate-up tap are
        # needed to avoid breaking the *next* run's navigation too.
        _cleanup_mismatched_field_dialog(client, apn, label)

    if toggle_coords and edit_field:
        # Efficiency improvement (client feedback, 2026-09-17): retyping
        # the ENTIRE value on every toggle-correction attempt is wasted
        # work — only ONE character needs probing to tell whether the
        # current mode is right or wrong. Probe with just the value's own
        # first character; only once that's confirmed correct is the
        # (much cheaper, now guaranteed-safe) rest of the value typed —
        # for real, exactly once, never retried, regardless of correction
        # count.
        #
        # Originally scoped to numeric_only fields only, on the theory
        # that romaji letters (unlike digits) can have a multi-keystroke
        # composing delay before anything commits, making a single-letter
        # probe less reliable there. Client feedback (2026-09-17,
        # observed on real SOG07 hardware) asked for the same treatment
        # on 名前/APN too — extended here to every field with a
        # configured toggle, since the retry loop's own read-back check
        # is robust to whatever the probe's actual committed length turns
        # out to be (it always backspaces the field's own reported
        # length, never an assumed one — see
        # _toggle_and_type_with_retry()'s comment). Whether a
        # single-letter probe is as reliable for romaji text as it is for
        # digits is NOT independently confirmed the way the numeric case
        # was — worth watching on the next real 名前/APN correction.
        probe, rest = value[0], value[1:]
        matched, actual = _toggle_and_type_with_retry(_type_fn(probe), probe)
        if matched is None:
            return False
        if not matched:
            _fail_mismatch(probe, actual, _KEYBOARD_TOGGLE_MAX_ATTEMPTS)
            return False
        if rest and not _type_fn(rest)():
            return False
        if edit_field:
            ui_xml = dump_ui(client)
            actual = get_node_text(ui_xml, edit_field)
            if actual != value:
                # Unexpected: the probe confirmed the mode was correct,
                # but the full value still doesn't match. Something else
                # is wrong — fail loudly rather than guess why.
                _fail_mismatch(value, actual, 1)
                return False
    else:
        matched, actual = _toggle_and_type_with_retry(_type_fn(value), value)
        if matched is None:
            return False
        if not matched:
            _fail_mismatch(value, actual, _KEYBOARD_TOGGLE_MAX_ATTEMPTS if toggle_coords else 1)
            return False

    confirm_button = apn.get("dialog_confirm_button_resource_id")
    if confirm_button and not tap_resource_id(client, confirm_button):
        logger.error(
            "apn field %r: dialog confirm button %r not found (real, "
            "confirmed id — see tests/fixtures/apn_accesshost_okbtn_SHG10.xml) "
            "— the value was typed but NOT committed, and the dialog is "
            "likely still open. Failing here rather than continuing: every "
            "later tap (next field, save) would otherwise land on this "
            "stuck dialog instead of its intended target.",
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


def _apn_entry_visible(ui_xml: str, apn_name: str) -> bool:
    """Best-effort check: does `apn_name` appear as visible text anywhere
    in this dump? Used for _save_apn()'s soft post-save confirmation —
    exceptions (e.g. AmbiguousResourceIdError-style ambiguity from
    find_by_text()) are treated as "not found" rather than propagated,
    since this is advisory only and must never itself cause a failure."""
    try:
        return find_by_text(ui_xml, apn_name) is not None
    except Exception:
        return False


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
      this check miss a genuinely successful save. Two retries before
      giving up: first waits `_POST_SAVE_RECHECK_DELAY_SECONDS` and dumps
      the same screen again (a real run, 2026-09-11, showed the list can
      take a moment to actually refresh after 保存); if that still doesn't
      find it, re-launches the `android.settings.APN_SETTINGS` intent to
      force a genuine screen reload (a later real run, 2026-09-15,
      SHG07, showed simply waiting on the already-open screen isn't
      always enough, but leaving and re-entering Settings does show the
      entry). Still soft either way — never a hard failure on its own.

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

        entry_visible = _apn_entry_visible(ui_xml, apn_name)
        if not entry_visible:
            # See _POST_SAVE_RECHECK_DELAY_SECONDS's comment — the list may
            # just not have refreshed yet. One retry before concluding.
            time.sleep(_POST_SAVE_RECHECK_DELAY_SECONDS)
            ui_xml = dump_ui(client)
            entry_visible = _apn_entry_visible(ui_xml, apn_name)

        if not entry_visible:
            # Real finding (2026-09-15, SHG07): even the delay+re-dump
            # above can still show a stale list — the client confirmed
            # manually that simply waiting on the SAME still-open screen
            # isn't always enough, but leaving and re-entering Settings
            # does show the entry. A fresh android.settings.APN_SETTINGS
            # intent forces the screen to actually reload from the
            # underlying data, unlike re-dumping an already-open one.
            # Still soft — a failure here only skips this last recheck,
            # never turns into a hard failure.
            try:
                client.shell("am start -a android.settings.APN_SETTINGS")
            except AdbCommandError as exc:
                logger.info(
                    "apn: re-navigation for the post-save recheck failed: %s", exc
                )
            else:
                ui_xml = dump_ui(client)
                entry_visible = _apn_entry_visible(ui_xml, apn_name)

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
    labeled-shape models by default, input_ascii_direct() instead when
    apn_settings.use_keyevent_text_entry is set — see
    _fill_labeled_field() — inject_text() for legacy-shape models). Tap
    save. Return True on success.

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

    # Diagnostic only — logged, never acted on. See input_ascii_direct()'s
    # docstring and get_current_ime()'s docstring for why: this project has
    # twice now (SHG10 MCC/MNC, SHG07 名前/APN) needed to actually see real
    # evidence of an IME-related field-entry problem to fix it correctly,
    # rather than guess. If a future model/device shows a similar symptom,
    # this line in its log is the first thing to check.
    current_ime = get_current_ime(client)
    if current_ime is not None:
        logger.info("apn: current input method is %r", current_ime)

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
        # MCC/MNC are marked numeric_only=True: real-device finding
        # (2026-09-11) showed input_text_direct() ("input text") commits
        # them as full-width digits on this device — see
        # _fill_labeled_field()'s docstring.
        fields = [
            (apn["name_field_label"], apn_name, False),
            (apn["apn_field_label"], apn_name, False),
            (apn["mcc_field_label"], mcc, True),
            (apn["mnc_field_label"], mnc, True),
        ]
        for label, value, numeric_only in fields:
            if not _fill_labeled_field(client, apn, label, value, numeric_only=numeric_only):
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
