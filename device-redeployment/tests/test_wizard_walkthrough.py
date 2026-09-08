"""Tests for src/phase2/wizard_walkthrough.py — both the legacy
sequence-driven schema (still used by 3 untouched models) and the Stage B
screen-driven text-matching schema (SHG10; see docs/record.md
'IMPLEMENTATION SPEC — wizard via text matching')."""

import pytest

from src.device.model_profile import ModelProfile
from src.device.ui_automator import ForbiddenTapTargetError
from src.phase2.wizard_walkthrough import run_wizard
from tests.fakes import FakeAdbClient

# --- Legacy sequence-driven -------------------------------------------------

LEGACY_PROFILE = ModelProfile(
    {
        "model": "Legacy Test",
        "model_number": "TST01",
        "manufacturer": "Test",
        "android_version": 13,
        "wizard_steps": [
            {"screen": "language_select", "resource_id": "wiz:next", "action": "tap"},
            {"screen": "skip_sim", "resource_id": "wiz:skip", "action": "tap", "optional": True},
        ],
        "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
        "apn_settings": {"menu_path": ["Settings"]},
    }
)

LEGACY_SCREEN_XML = """<hierarchy>
  <node resource-id="wiz:next" bounds="[0,0][100,100]" />
</hierarchy>"""


def test_legacy_wizard_full_success_optional_step_missing():
    client = FakeAdbClient(ui_dumps=[LEGACY_SCREEN_XML])
    result = run_wizard(client, LEGACY_PROFILE, max_attempts=1, retry_delay_seconds=0)
    assert result is True


def test_legacy_wizard_required_step_missing_fails():
    profile = ModelProfile(
        {
            "model": "Legacy Test",
            "model_number": "TST01",
            "manufacturer": "Test",
            "android_version": 13,
            "wizard_steps": [{"screen": "x", "resource_id": "missing", "action": "tap"}],
            "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
            "apn_settings": {"menu_path": ["Settings"]},
        }
    )
    client = FakeAdbClient(ui_dumps=["<hierarchy></hierarchy>"])
    result = run_wizard(client, profile, max_attempts=1, retry_delay_seconds=0)
    assert result is False


# --- Screen-driven, text-matching (Stage B / SHG10) -------------------------

SCREEN_DRIVEN_SCREENS = [
    {"name": "welcome", "identify_by_text": "ようこそ", "action": "tap_by_text", "target_text": "開始"},
    {"name": "carrier_setup", "identify_by_text": "キャリア設定中", "action": "wait_for_disappear", "timeout_sec": 5},
    {"name": "wifi_connect", "identify_by_text": "Wi-Fiに接続", "action": "tap_by_text", "target_text": "オフラインで設定"},
    {"name": "google_terms", "identify_by_text": "同意する", "action": "scroll_then_tap_by_text", "target_text": "同意する"},
    {"name": "aquos_notify", "identify_by_text": "AQUOS Homeの通知アクセス", "action": "tap_by_text", "target_text": "OK"},
]


def _screen_driven_profile(screens=SCREEN_DRIVEN_SCREENS) -> ModelProfile:
    return ModelProfile(
        {
            "model": "SHG10-like Test",
            "model_number": "TST02",
            "manufacturer": "Test",
            "android_version": 14,
            "wizard": {"screens": screens},
            "wifi_settings": {"toggle_resource_id": "t", "network_list_resource_id": "n"},
            "apn_settings": {"menu_path": ["Settings"]},
        }
    )


def _xml(*node_texts) -> str:
    nodes = "".join(
        f'<node text="{t}" bounds="[0,{i*100}][200,{i*100+100}]" />' for i, t in enumerate(node_texts)
    )
    return f"<hierarchy>{nodes}</hierarchy>"


# Each screen turn consumes an exact, deterministic number of dump_ui() calls:
# one outer "which screen is this" scan, plus however many the action itself
# performs internally (tap_by_text: 1; wait_for_disappear: however many polls
# until the text is gone, here always exactly 1 by construction; scroll_then_
# tap_by_text: 3 — a first tap attempt, scroll_down's own dump for screen
# bounds, then a second tap attempt). The lists below are built to that exact
# count rather than "enough repeats to probably work", since padding with
# extra repeats of an already-consumed screen leaves stale copies that then
# fail to match anything (the screen they belong to is already `done`).

WELCOME_XML = _xml("ようこそ", "開始")
WIFI_CONNECT_XML = _xml("Wi-Fiに接続", "オフラインで設定")
GOOGLE_TERMS_XML = _xml("同意する")
AQUOS_NOTIFY_XML = _xml("AQUOS Homeの通知アクセス", "OK")
CARRIER_SPINNER_XML = _xml("キャリア設定中")


def test_screen_driven_full_sequence_with_carrier_setup_present():
    screens = [
        {"name": "welcome", "identify_by_text": "ようこそ", "action": "tap_by_text", "target_text": "開始"},
        {"name": "carrier_setup", "identify_by_text": "キャリア設定中", "action": "wait_for_disappear", "timeout_sec": 5},
        {"name": "wifi_connect", "identify_by_text": "Wi-Fiに接続", "action": "tap_by_text", "target_text": "オフラインで設定"},
        {"name": "aquos_notify", "identify_by_text": "AQUOS Homeの通知アクセス", "action": "tap_by_text", "target_text": "OK"},
    ]
    client = FakeAdbClient(
        ui_dumps=[
            WELCOME_XML, WELCOME_XML,              # welcome: scan, action-tap
            CARRIER_SPINNER_XML, WIFI_CONNECT_XML,  # carrier_setup: scan (spinner up), wait-exit-check (gone)
            WIFI_CONNECT_XML, WIFI_CONNECT_XML,     # wifi_connect: fresh scan, action-tap
            AQUOS_NOTIFY_XML, AQUOS_NOTIFY_XML,     # aquos_notify: scan, action-tap (terminal, returns immediately)
        ]
    )
    result = run_wizard(client, _screen_driven_profile(screens))
    assert result is True


def test_screen_driven_skips_conditional_carrier_screen_when_absent():
    """carrier_setup's 「キャリア設定中」 never appears at all — the flow must
    still complete via the later screens, not fail or hang waiting for it."""
    screens = [
        {"name": "welcome", "identify_by_text": "ようこそ", "action": "tap_by_text", "target_text": "開始"},
        {"name": "carrier_setup", "identify_by_text": "キャリア設定中", "action": "wait_for_disappear", "timeout_sec": 5},
        {"name": "wifi_connect", "identify_by_text": "Wi-Fiに接続", "action": "tap_by_text", "target_text": "オフラインで設定"},
        {"name": "aquos_notify", "identify_by_text": "AQUOS Homeの通知アクセス", "action": "tap_by_text", "target_text": "OK"},
    ]
    client = FakeAdbClient(
        ui_dumps=[
            WELCOME_XML, WELCOME_XML,
            WIFI_CONNECT_XML, WIFI_CONNECT_XML,  # goes straight here — carrier_setup's identify text never appears
            AQUOS_NOTIFY_XML, AQUOS_NOTIFY_XML,
        ]
    )
    result = run_wizard(client, _screen_driven_profile(screens))
    assert result is True


def test_screen_driven_scrolls_when_target_not_immediately_visible():
    # A scrollable terms screen where the identify text and button text
    # differ, so a "before scroll" dump can show the screen without yet
    # showing its accept button.
    screens = [
        {"name": "welcome", "identify_by_text": "ようこそ", "action": "tap_by_text", "target_text": "開始"},
        {
            "name": "google_terms",
            "identify_by_text": "利用規約",
            "action": "scroll_then_tap_by_text",
            "target_text": "同意する",
        },
        {"name": "aquos_notify", "identify_by_text": "AQUOS Homeの通知アクセス", "action": "tap_by_text", "target_text": "OK"},
    ]
    pre_scroll = _xml("利用規約")
    post_scroll = _xml("利用規約", "同意する")
    client = FakeAdbClient(
        ui_dumps=[
            WELCOME_XML, WELCOME_XML,
            pre_scroll,   # scan
            pre_scroll,   # action's first tap attempt (target not yet visible)
            pre_scroll,   # scroll_down()'s own dump (just needs screen bounds)
            post_scroll,  # action's second tap attempt (target now visible)
            AQUOS_NOTIFY_XML, AQUOS_NOTIFY_XML,
        ]
    )
    result = run_wizard(client, _screen_driven_profile(screens))
    assert result is True
    assert any(c.startswith("input swipe") for c in client.shell_calls)


def test_screen_driven_unrecognized_screen_fails_loudly():
    client = FakeAdbClient(ui_dumps=[_xml("Some Completely Unknown Screen")])
    result = run_wizard(client, _screen_driven_profile())
    assert result is False


def test_screen_driven_unverified_target_text_fails_closed():
    """A screen whose button label is unverified (docs/record.md: 「ようこそ」
    and 「ソフトウェア更新について」) is configured with a literal
    "TODO(verify)" placeholder target_text. That text will never match
    anything real, so the wizard must fail loudly rather than tap something
    else by mistake."""
    screens = [
        {"name": "welcome", "identify_by_text": "ようこそ", "action": "tap_by_text", "target_text": "TODO(verify)"},
    ]
    client = FakeAdbClient(ui_dumps=[_xml("ようこそ", "開始")])
    result = run_wizard(client, _screen_driven_profile(screens))
    assert result is False


def test_screen_driven_never_taps_forbidden_text_even_if_misconfigured():
    """Defense in depth: even if a screen definition were mistakenly
    configured to tap 戻る/中断, the ui_automator-level guard must still
    block it rather than the wizard silently doing so."""
    screens = [
        {"name": "bad", "identify_by_text": "セットアップを続けますか?", "action": "tap_by_text", "target_text": "戻る"},
    ]
    client = FakeAdbClient(ui_dumps=[_xml("セットアップを続けますか?", "戻る")])
    with pytest.raises(ForbiddenTapTargetError):
        run_wizard(client, _screen_driven_profile(screens))
