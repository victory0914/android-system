"""UI Automator helpers: dumping the current screen's view hierarchy and
locating/tapping elements within it by resource-id, visible text, or
accessibility content-desc.

This module knows nothing about Wi-Fi/APN/wizard specifics — it only
understands the generic `uiautomator dump` XML schema
(`<hierarchy><node resource-id="..." bounds="[x1,y1][x2,y2]" text="..."
content-desc="..." checked="..." class="..." .../></hierarchy>`), which is a
stable, documented Android platform format that does not vary by
manufacturer. `navigate_menu_path()` is the one exception to "no app
knowledge" in spirit only — it's still generic (a caller-supplied list of
{type, value} steps), it just happens to be used for Wi-Fi/APN navigation.

Stage B addition: real `uiautomator dump` captures from SHG10 (see
tests/fixtures/*_SHG10.xml, docs/record.md) showed that individual list rows
(Wi-Fi networks, APN edit-form fields) do NOT carry a per-row resource-id —
they all share one generic id (e.g. `android:id/title`) and are
distinguished only by their `text`. Icon-only controls (overflow menu,
"navigate up") go further: no resource-id AND no visible text, only a
`content-desc`. `find_by_content_desc`/`tap_by_content_desc` exist for that
case. See PENDING_REAL_DEVICE_DATA.md for what's still unresolved.
"""

from __future__ import annotations

import re
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from src.device.adb_client import AdbClientProtocol, AdbCommandError

_REMOTE_DUMP_DIR = "/sdcard"
_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

# The "USB debugging connected — tap here to disable" notification observed
# in the shade during SHG10 sessions (docs/record.md, "UI hazard" section).
# A mistargeted tap on it disables ADB and permanently strands the device
# mid-run. We have no captured dump of the notification itself (its bounds
# are unknown), so rather than compute an exclusion zone we don't have real
# coordinates for, any screen containing this text is refused entirely.
_HAZARD_TEXT_MARKERS = (
    "USBデバッグが接続されました",
    "無効にするにはここをタップ",
)

# Text that must never be tapped, no matter what config says to look for —
# either they reverse/abort a flow (the wizard's 戻る/中断し...) or they're
# destructive actions found near where automation operates (Wi-Fi's
# 削除/接続を解除 — real testing, 2026-09-08, showed a retry that landed on an
# already-connected network's "Network Details" screen instead of the
# expected join dialog; nothing there was explicitly tap_by_text()'d, but
# this list is kept as a last-resort guard at the tap layer itself in case
# any future path does target these). Kept here, not just in per-model
# config, so it can't be configured away by mistake.
_NEVER_TAP_TEXT = (
    "戻る",
    "中断し、リマインダーを受け取る",
    "削除",
    "接続を解除",
)


class AmbiguousResourceIdError(Exception):
    """Raised when a resource_id/text/content_desc match finds more than one
    node in the UI dump and no `index` was given to disambiguate. Silently
    tapping the wrong list row (e.g. the wrong Wi-Fi network) is worse than
    failing loudly, so this is raised rather than guessing the first match."""


class HazardousScreenError(Exception):
    """Raised when the current screen contains a known-hazardous element —
    currently just the USB-debugging-disable notification — and a tap was
    about to be attempted. Refuses to act on the *whole* screen rather than
    trying to carve out a safe exclusion zone we have no captured bounds
    for. See docs/record.md, 'UI hazard' section."""


class ForbiddenTapTargetError(Exception):
    """Raised when code asks to tap text that's on the permanent do-not-tap
    list (e.g. a wizard's 「戻る」/back button) — these reverse or abort a
    flow and must never be tapped programmatically, even by mistake."""


_DUMP_MAX_ATTEMPTS = 3
_DUMP_RETRY_DELAY_SECONDS = 1.0


def _dump_ui_once(client: AdbClientProtocol) -> str:
    """Single dump+pull attempt, no retry. Raises AdbCommandError if the
    pull fails — real-hardware testing (2026-09-08) found this used to be
    silently unchecked, so a failed pull (uiautomator dump not having
    written the file yet — a known intermittent issue right after a screen
    transition) crashed with a raw FileNotFoundError from reading a file
    that was never created, instead of a clear, retriable error."""
    remote_path = f"{_REMOTE_DUMP_DIR}/window_dump_{uuid.uuid4().hex}.xml"
    client.shell(f"uiautomator dump {remote_path}")
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            local_path = str(Path(tmp_dir) / "window_dump.xml")
            if not client.pull(remote_path, local_path):
                raise AdbCommandError(
                    f"pull {remote_path}",
                    "uiautomator dump pull failed (file may not have been "
                    "ready yet — uiautomator dump is known to intermittently "
                    "fail right after a screen transition)",
                )
            return Path(local_path).read_text(encoding="utf-8")
    finally:
        # Best-effort cleanup of the on-device temp file — don't fail the
        # whole dump just because cleanup couldn't run.
        try:
            client.shell(f"rm -f {remote_path}")
        except Exception:
            pass


def dump_ui(client: AdbClientProtocol) -> str:
    """Run `uiautomator dump`, pull the resulting XML via the client, and
    return it as a string. Cleans up the on-device temp file afterward.

    Retries a few times on failure: `uiautomator dump` is known to
    intermittently fail to produce a readable file (e.g. right after a
    screen transition) — confirmed on real hardware, 2026-09-08 (APN menu
    navigation, immediately after a screen change). Most calls succeed on
    the first try; this only adds latency on the rare failure.
    """
    last_error: Exception | None = None
    for attempt in range(1, _DUMP_MAX_ATTEMPTS + 1):
        try:
            return _dump_ui_once(client)
        except (AdbCommandError, OSError) as exc:
            last_error = exc
            if attempt < _DUMP_MAX_ATTEMPTS:
                time.sleep(_DUMP_RETRY_DELAY_SECONDS)
    raise AdbCommandError(
        "uiautomator dump", f"failed after {_DUMP_MAX_ATTEMPTS} attempts: {last_error}"
    )


def _raise_if_hazardous(ui_xml: str) -> None:
    for marker in _HAZARD_TEXT_MARKERS:
        if marker in ui_xml:
            raise HazardousScreenError(
                "refusing to tap: current screen contains the USB-debugging "
                f"disable notification (matched {marker!r} in the dump). A "
                "mistargeted tap here would disable ADB and strand the "
                "device. Clear the notification shade before retrying — "
                "see docs/record.md, 'UI hazard' section."
            )


def _parse_bounds_rect(bounds: str) -> tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.match(bounds)
    if not match:
        return None
    x1, y1, x2, y2 = (int(v) for v in match.groups())
    return x1, y1, x2, y2


def _parse_bounds(bounds: str) -> tuple[int, int] | None:
    rect = _parse_bounds_rect(bounds)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    return (x1 + x2) // 2, (y1 + y2) // 2


def _node_center(node: ET.Element) -> tuple[int, int] | None:
    bounds = node.get("bounds")
    if not bounds:
        return None
    return _parse_bounds(bounds)


def _iter_all_matches(
    root: ET.Element,
    *,
    resource_id: str | None = None,
    text: str | None = None,
    content_desc: str | None = None,
) -> list[ET.Element]:
    """AND-filter every <node> by whichever of resource-id/text/content-desc
    was given (None = don't filter on that attribute)."""
    matches = []
    for node in root.iter("node"):
        if resource_id is not None and node.get("resource-id") != resource_id:
            continue
        if text is not None and node.get("text") != text:
            continue
        if content_desc is not None and node.get("content-desc") != content_desc:
            continue
        matches.append(node)
    return matches


def _disambiguate_or_raise(
    matches: list[ET.Element], index: int, what_matched: str
) -> ET.Element | None:
    """Shared index/ambiguity resolution for find_by_text()/
    find_by_content_desc() (find_resource_id() has its own variant since its
    `text` parameter is a secondary narrowing filter, not the primary
    match). See the `index=0` caveat on find_resource_id for why a bare
    `index=0` still raises on multiple matches rather than picking the
    first silently."""
    if index != 0:
        if index >= len(matches):
            return None
        return matches[index]
    if len(matches) > 1:
        raise AmbiguousResourceIdError(
            f"{what_matched} matched {len(matches)} nodes; pass `index` to "
            "disambiguate instead of guessing."
        )
    return matches[0]


def find_resource_id(
    ui_xml: str,
    resource_id: str,
    *,
    text: str | None = None,
    index: int = 0,
) -> tuple[int, int] | None:
    """Parse the UI dump XML and return the (x, y) center of the matching
    node's 'bounds' attribute, or None if not found.

    Supports:
      - matching by resource_id alone (returns the first/only match — fine
        for one-off elements like buttons)
      - matching by resource_id AND text (e.g. find the Wi-Fi row whose
        text equals a specific SSID) — real captures show this is the
        common case: rows share one generic resource-id like
        `android:id/title` and are distinguished only by text.
      - matching by resource_id AND index (the Nth matching node, 0-based)

    Raises AmbiguousResourceIdError if multiple nodes match resource_id and
    neither text nor index was given to disambiguate.

    Note on `index=0`: because 0 is also this parameter's default, a bare
    `index=0` is indistinguishable from "index not given" and therefore
    still raises AmbiguousResourceIdError on multiple matches rather than
    silently picking the first one — only a non-zero index (1, 2, ...)
    counts as an explicit disambiguation request. To deliberately select the
    first of several ambiguous nodes, disambiguate by `text` instead. This
    is a deliberate call-site guardrail against accidentally-silent
    first-match behavior, not an oversight.
    """
    root = ET.fromstring(ui_xml)
    matches = _iter_all_matches(root, resource_id=resource_id)

    if not matches:
        return None

    if text is not None:
        text_matches = [node for node in matches if node.get("text") == text]
        if not text_matches:
            return None
        target = text_matches[0]
    else:
        target = _disambiguate_or_raise(matches, index, f"resource_id {resource_id!r}")
        if target is None:
            return None

    return _node_center(target)


def find_by_text(
    ui_xml: str,
    text: str,
    *,
    index: int = 0,
) -> tuple[int, int] | None:
    """Like find_resource_id(), but matches on the node's visible `text`
    instead of its resource-id.

    This exists for screens where a stable per-model resource-id isn't
    something we can define up front — e.g. walking a generic Settings menu
    path, or a wizard screen identified only by its visible label. Same
    disambiguation rules as find_resource_id(): raises
    AmbiguousResourceIdError if `text` matches multiple nodes and no `index`
    was given (see the `index=0` caveat on find_resource_id).
    """
    root = ET.fromstring(ui_xml)
    matches = _iter_all_matches(root, text=text)

    if not matches:
        return None

    target = _disambiguate_or_raise(matches, index, f"text {text!r}")
    if target is None:
        return None

    return _node_center(target)


def find_by_content_desc(
    ui_xml: str,
    content_desc: str,
    *,
    index: int = 0,
) -> tuple[int, int] | None:
    """Like find_by_text(), but matches on the node's `content-desc`
    (accessibility description) instead of visible `text`.

    Needed for icon-only controls that have neither a stable resource-id nor
    a visible text label — e.g. the overflow "..." menu button
    (content-desc "その他のオプション") or a toolbar "navigate up" arrow
    (content-desc "上へ移動"), both observed on real SHG10 dumps with
    resource-id="" and no `text`. Same disambiguation rules as
    find_by_text().
    """
    root = ET.fromstring(ui_xml)
    matches = _iter_all_matches(root, content_desc=content_desc)

    if not matches:
        return None

    target = _disambiguate_or_raise(matches, index, f"content_desc {content_desc!r}")
    if target is None:
        return None

    return _node_center(target)


def node_is_checked(
    ui_xml: str,
    resource_id: str,
    *,
    text: str | None = None,
    index: int = 0,
) -> bool | None:
    """Return the matched node's `checked` attribute as a bool, or None if
    no matching node is found. Same matching/disambiguation rules as
    find_resource_id().

    Exists so callers can check a toggle/switch's current state before
    deciding whether to tap it — e.g. don't blindly tap a Wi-Fi on/off
    switch without first checking whether it's already on, or a "tap to
    enable" action can end up disabling it instead.
    """
    root = ET.fromstring(ui_xml)
    matches = _iter_all_matches(root, resource_id=resource_id)

    if not matches:
        return None

    if text is not None:
        text_matches = [node for node in matches if node.get("text") == text]
        if not text_matches:
            return None
        target = text_matches[0]
    else:
        target = _disambiguate_or_raise(matches, index, f"resource_id {resource_id!r}")
        if target is None:
            return None

    return target.get("checked") == "true"


def get_node_text(
    ui_xml: str,
    resource_id: str,
    *,
    index: int = 0,
) -> str | None:
    """Return the matched node's `text` attribute, or None if no matching
    node is found. Same matching/disambiguation rules as find_resource_id()
    (minus the secondary `text=` filter, which wouldn't make sense here —
    this function *reads* text, it doesn't search by it).

    Exists to read dialog/message content rather than just detect a node's
    presence or tap it — e.g. a real SHG10 capture showed APN save
    validation failures render as a standard AlertDialog with the actual
    error message at `android:id/message`; failing loudly means logging
    that real message, not just "something went wrong".
    """
    root = ET.fromstring(ui_xml)
    matches = _iter_all_matches(root, resource_id=resource_id)

    if not matches:
        return None

    target = _disambiguate_or_raise(matches, index, f"resource_id {resource_id!r}")
    if target is None:
        return None

    return target.get("text")


def all_visible_texts(ui_xml: str) -> list[str]:
    """Return every non-empty `text` attribute in the dump, in document
    order. Used to log a screen's full visible content when nothing
    recognized on it matches, so the missing screen/label can be added to
    config instead of the caller tapping blindly (see wizard_walkthrough.py,
    which fails loudly rather than guess on an unrecognized screen)."""
    root = ET.fromstring(ui_xml)
    return [node.get("text") for node in root.iter("node") if node.get("text")]


def _screen_bounds(ui_xml: str) -> tuple[int, int] | None:
    """Return (width, height) from the dump's outermost node's `bounds`
    (e.g. "[0,0][1080,2432]"), or None if it can't be parsed. Used to
    compute scroll gestures relative to the actual screen size in the dump
    just taken, rather than hardcoding a per-model pixel constant we have no
    captured value for."""
    root = ET.fromstring(ui_xml)
    first = next(root.iter("node"), None)
    if first is None:
        return None
    bounds = first.get("bounds")
    if not bounds:
        return None
    rect = _parse_bounds_rect(bounds)
    if rect is None:
        return None
    x1, y1, x2, y2 = rect
    return x2 - x1, y2 - y1


def tap_resource_id(
    client: AdbClientProtocol,
    resource_id: str,
    *,
    text: str | None = None,
    index: int = 0,
) -> bool:
    """Dump the UI, locate resource_id (optionally disambiguated by text or
    index), tap its center coordinates via `adb shell input tap x y`.
    Return False (not an exception) if the element is not present, so
    callers can treat an optional wizard step as a no-op rather than a hard
    failure. AmbiguousResourceIdError still propagates — an ambiguous match
    is a bug to fix, not a missing element to shrug off. Raises
    HazardousScreenError instead of tapping anything if the current screen
    contains the USB-debugging-disable notification."""
    ui_xml = dump_ui(client)
    _raise_if_hazardous(ui_xml)
    coords = find_resource_id(ui_xml, resource_id, text=text, index=index)
    if coords is None:
        return False
    x, y = coords
    client.shell(f"input tap {x} {y}")
    return True


def tap_by_text(client: AdbClientProtocol, text: str, *, index: int = 0) -> bool:
    """Dump the UI, locate a node by its visible `text` (see find_by_text()),
    tap its center coordinates. Return False if not present. Raises
    ForbiddenTapTargetError instead of tapping if `text` is on the permanent
    do-not-tap list (e.g. 「戻る」) — see _NEVER_TAP_TEXT. Raises
    HazardousScreenError instead of tapping anything if the current screen
    contains the USB-debugging-disable notification."""
    if text in _NEVER_TAP_TEXT:
        raise ForbiddenTapTargetError(
            f"refusing to tap {text!r}: this text is on the permanent "
            "do-not-tap list (reverses or aborts a flow)."
        )
    ui_xml = dump_ui(client)
    _raise_if_hazardous(ui_xml)
    coords = find_by_text(ui_xml, text, index=index)
    if coords is None:
        return False
    x, y = coords
    client.shell(f"input tap {x} {y}")
    return True


def tap_by_content_desc(
    client: AdbClientProtocol, content_desc: str, *, index: int = 0
) -> bool:
    """Dump the UI, locate a node by its `content-desc` (see
    find_by_content_desc()), tap its center coordinates. Return False if not
    present. Raises HazardousScreenError instead of tapping anything if the
    current screen contains the USB-debugging-disable notification."""
    ui_xml = dump_ui(client)
    _raise_if_hazardous(ui_xml)
    coords = find_by_content_desc(ui_xml, content_desc, index=index)
    if coords is None:
        return False
    x, y = coords
    client.shell(f"input tap {x} {y}")
    return True


def tap_left_of_content_desc(
    client: AdbClientProtocol, anchor_content_desc: str, *, index: int = 0
) -> bool:
    """Tap an ESTIMATED position immediately to the left of a node
    identified by `anchor_content_desc`, assuming a same-width icon
    occupies that adjacent space with no gap.

    For an icon-only control that has no identifier of its own (no
    resource-id, no text, and its own content-desc was never captured)
    but sits directly next to one that does. Confirmed real use case
    (2026-09-11): the APN list's "+" add button sits immediately left of
    the "⋮" overflow menu (content-desc "その他のオプション", itself
    confirmed real). This is a position ESTIMATE derived from the
    anchor's own real, dumped bounds — not a captured value for the
    target itself — so it can only confirm the anchor was found, not that
    the tap actually landed on the intended control; callers should still
    verify the expected next screen appears rather than trust this alone.
    """
    ui_xml = dump_ui(client)
    _raise_if_hazardous(ui_xml)
    root = ET.fromstring(ui_xml)
    matches = _iter_all_matches(root, content_desc=anchor_content_desc)
    if not matches:
        return False
    target = _disambiguate_or_raise(matches, index, f"content_desc {anchor_content_desc!r}")
    if target is None:
        return False
    bounds = target.get("bounds")
    if not bounds:
        return False
    rect = _parse_bounds_rect(bounds)
    if rect is None:
        return False
    x1, y1, x2, y2 = rect
    width = x2 - x1
    estimated_x = x1 - width // 2
    estimated_y = (y1 + y2) // 2
    client.shell(f"input tap {estimated_x} {estimated_y}")
    return True


def scroll_down(client: AdbClientProtocol, *, duration_ms: int = 300) -> None:
    """Swipe up (revealing content further down the page) by an amount
    computed from the *current* screen's own dumped bounds, so no per-model
    pixel constant has to be invented. Used e.g. for a scrollable terms
    screen where the accept button may be below the fold (docs/record.md:
    the wizard's 「同意する」 screen)."""
    ui_xml = dump_ui(client)
    _raise_if_hazardous(ui_xml)
    size = _screen_bounds(ui_xml)
    if size is None:
        raise AdbCommandError(
            "scroll_down", "could not determine screen bounds from the UI dump"
        )
    width, height = size
    x = width // 2
    y_start = int(height * 0.8)
    y_end = int(height * 0.2)
    client.shell(f"input swipe {x} {y_start} {x} {y_end} {duration_ms}")


def wait_for_text_to_disappear(
    client: AdbClientProtocol,
    text: str,
    *,
    timeout_seconds: float = 60,
    poll_interval_seconds: float = 2.0,
) -> bool:
    """Poll dump_ui() until a node with this exact `text` is no longer
    present — for spinner/progress screens with no button to tap (e.g.
    docs/record.md's 「キャリア設定中」 / 「スマートフォンを設定しています」),
    where the correct action is to wait for the screen to go away, not try
    to tap it. Returns True once gone, False if still present at timeout."""
    deadline = time.monotonic() + timeout_seconds
    while True:
        ui_xml = dump_ui(client)
        _raise_if_hazardous(ui_xml)
        try:
            present = find_by_text(ui_xml, text) is not None
        except AmbiguousResourceIdError:
            present = True  # multiple matches still means "still on screen"
        if not present:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval_seconds)


def navigate_menu_path(client: AdbClientProtocol, steps: list) -> bool:
    """Walk a sequence of navigation steps, each identifying one menu item to
    tap by exactly one mechanism:

        {"type": "text", "value": "..."}          -> tap_by_text
        {"type": "resource_id", "value": "..."}   -> tap_resource_id
        {"type": "content_desc", "value": "..."}  -> tap_by_content_desc

    A bare string step (Stage A's original menu_path shape — still used by
    models not yet updated with real per-step navigation data) is treated as
    `{"type": "text", "value": <that string>}`.

    Stops and returns False the moment a step isn't found, rather than
    guessing past a missing menu item. Lives here (not in phase2/*) because
    it's pure UI-dump navigation with no Wi-Fi/APN-specific knowledge — the
    *meaning* of the steps (which menu leads where) is entirely supplied by
    the caller's config.
    """
    dispatch = {
        "text": lambda value: tap_by_text(client, value),
        "resource_id": lambda value: tap_resource_id(client, value),
        "content_desc": lambda value: tap_by_content_desc(client, value),
    }
    for step in steps:
        if isinstance(step, str):
            step_type, value = "text", step
        else:
            step_type, value = step.get("type", "text"), step["value"]
        action = dispatch.get(step_type)
        if action is None:
            raise ValueError(f"navigate_menu_path: unknown step type {step_type!r}")
        if not action(value):
            return False
    return True


def inject_text(client: AdbClientProtocol, text: str) -> bool:
    """Inject literal text via ADB Keyboard (assumes it's already installed
    and set as the active IME). Return True on success."""
    # ADB Keyboard listens for this broadcast intent with base64-free raw text
    # via the ADB_INPUT_TEXT extra. Quote to keep the shell from splitting on
    # whitespace/special characters in `text`.
    escaped = text.replace('"', '\\"')
    client.shell(
        f'am broadcast -a ADB_INPUT_TEXT --es msg "{escaped}"'
    )
    return True


def input_text_direct(client: AdbClientProtocol, text: str) -> bool:
    """Type text via Android's built-in `input text` shell command —
    injected directly through instrumentation, not through the active IME.

    Unlike inject_text() (broadcasts to ADB Keyboard, which needs that app
    installed and set as the active input method), this needs no extra app.
    Real-device testing (docs/record.md, 2026-09-08) found it necessary
    for APN's MCC/MNC fields specifically: the device's default IME is in
    Japanese kana mode, and the on-screen keyboard can't reach digits
    without an explicit mode switch UI automation has no reliable way to
    trigger. A second real run (2026-09-08, Wi-Fi password entry) found
    inject_text()'s ADB Keyboard broadcast silently does nothing at all on
    this device — the password field stayed empty despite no errors,
    consistent with ADB Keyboard not actually being installed/active —
    so this is now the primary text-entry mechanism for this device, not
    just a numeric-field workaround.

    `adb shell <command>` runs `<command>` through the *device's* shell, so
    the value is escaped for a POSIX-ish shell inside a double-quoted
    string: backslash, double-quote, `$`, and backtick (which would
    otherwise trigger escaping/expansion inside double quotes) are escaped,
    and literal spaces become `%s` (`input text`'s own convention). This
    matters more here than it did for MCC/MNC (pure digits) — passwords
    routinely contain exactly these characters.
    """
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
        .replace(" ", "%s")
    )
    client.shell(f'input text "{escaped}"')
    return True


def input_digits_direct(client: AdbClientProtocol, digits: str) -> bool:
    """Type a string of ASCII digits one at a time via `adb shell input
    keyevent KEYCODE_<n>` — NOT input_text_direct()'s `input text`.

    Real-device finding (client report, 2026-09-11): on this device,
    `input text "440"` for APN's MCC/MNC fields commits as FULL-WIDTH
    digits (e.g. "４４０") instead of half-width/ASCII ("440"), even
    though input_text_direct() is meant to bypass the active IME entirely.
    The device's default IME is Japanese kana mode (see
    input_text_direct()'s docstring); it's not confirmed exactly why
    `input text` picks up its zenkaku conversion when individual digit
    keyevents evidently don't, but per-digit KEYCODE_0..KEYCODE_9 events
    map directly to the physical/virtual number-row keys and have always
    been the standard way to guarantee literal ASCII digit entry
    regardless of IME state — safer to rely on here than to guess further
    at why `input text` misbehaves.

    Raises ValueError if `digits` isn't purely ASCII 0-9 — this exists
    specifically for MCC/MNC, which are pre-validated against
    _MCC_PATTERN/_MNC_PATTERN before this is ever called; anything else
    reaching here is a caller bug, not a device quirk to route around.
    """
    if not digits.isascii() or not digits.isdigit():
        raise ValueError(f"input_digits_direct() only accepts ASCII digits, got {digits!r}")
    for digit in digits:
        client.shell(f"input keyevent KEYCODE_{digit}")
    return True
