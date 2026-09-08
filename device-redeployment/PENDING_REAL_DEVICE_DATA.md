# Pending Real-Device Data

Tracks every placeholder value and open assumption still needing real-device
confirmation, so work can resume cleanly without re-deriving what's
outstanding. See `docs/record.md` for the full session notes (test logs,
navigation paths, capture methodology, judgment calls) behind every entry
here — this file is the checklist; that one is the evidence.

**Status as of 2026-09-08 (Stage B, partial):** SHG10 has real Wi-Fi + APN
data resolved from actual `uiautomator dump` captures
(`tests/fixtures/*_SHG10.xml`). SHG10's wizard is on a photograph-derived,
text-matching config — real dumps for the wizard are **not obtainable on any
model, ever** (structural ADB/factory-reset constraint, see docs/record.md).
**SOG08, SOG07, and SHG07 are entirely untouched** — still 100% Stage A
placeholders, not started.

## Highest priority

### SHG10 APN: no Save action exists anywhere in the captured form

Checked all three scroll positions (top/middle/bottom) of the real APN edit
form — there is no Save button. `apn_settings.save_button_resource_id` is
`null` and `configure_apn()` fails loudly (returns False, logs clearly)
rather than guessing. Until this is resolved, **SHG10's APN configuration
cannot complete**, even though field entry itself works. Two unconfirmed
candidates were recorded (`apn_settings.save_action_candidates` in the
model YAML) for the next on-site session to test — neither is wired into
any code path:
- overflow "..." menu, content-desc `その他のオプション` (contents not captured)
- toolbar "navigate up" arrow, content-desc `上へ移動` (matches stock AOSP
  ApnEditor's save-on-up-navigation behavior; unconfirmed on this SHARP build)

This is the single highest-priority item — everything else resolved for
SHG10 is only useful once this unblocks a full run.

### Wi-Fi list disambiguation — RESOLVED for SHG10, still open for the other 3

Real capture confirmed the risk Stage A anticipated: `android:id/title` is
shared by every row on the Wi-Fi/mobile-network combined screen (9 matches
in one dump — the carrier summary row, the Wi-Fi toggle's own label, and
7 scanned SSIDs), and near-duplicate SSID pairs exist at the client site.
`find_resource_id()` correctly raises `AmbiguousResourceIdError` without
`text=`, and correctly disambiguates the real pairs — see
`tests/test_real_shg10_fixtures.py`. The real pairs, replacing the
hypothetical example from Stage A:
- `ARIZASU-WiFi-6F_2.4GHz` / `ARIZASU-WiFi-6F_5G`
- `SPWH_L13_72E834` / `SPWH_L13_72E834_5G`
- Others seen (not near-duplicates): `HR02b-BA15BA`, `earth2.4_6`, `earth5_1`

**SOG08/SOG07/SHG07 have no Wi-Fi dump yet at all** — this remains the
top-priority unstarted item for those three models specifically.

## SHG10 (AQUOS sense7, SHARP/KDDI, Android 14) — Stage B, partial

**Corrected finding:** real `adb` identification reported Android 14
(`[SHARP] KDDI SHG10 (Android 14)`), not Android 12 as the original task
spec assumed. Config and tests now reflect 14.

### Resolved (real captures — `tests/fixtures/wifi_list_SHG10.xml`,
`apn_entry_{top,middle,bottom}_SHG10.xml`)
- `wifi_settings.toggle_resource_id` = `android:id/switch_widget` (unambiguous,
  single match — but see "toggle must be checked, not blindly tapped" below)
- `wifi_settings.network_list_resource_id` = `android:id/title` (generic,
  must be paired with `text=<SSID>`)
- `wifi_settings.menu_path` — confirmed navigation path (screen text, not a
  dump, but observed via live scrcpy mirroring): 設定 →
  ネットワークとインターネット → Wi-Fi とモバイルネットワーク
- `apn_settings.menu_path` — confirmed: same as above, then the gear icon
  next to the carrier name (`com.android.settings:id/settings_button` —
  real, unambiguous resource-id, unlike the icons below) → アクセスポイント名
- `apn_settings.field_row_resource_id` = `android:id/title` (generic, shared
  by every field on the edit form — 名前/APN/プロキシ/ポート/ユーザー名/
  パスワード/サーバー/MMSC/MMSプロキシ/MMSポート/MCC/MNC/認証タイプ/APNタイプ/
  APNプロトコル/APNローミングプロトコル/ベアラー/MVNOの種類/MVNO値 all share it)
- `apn_settings.name_field_label` = `名前`, `apn_field_label` = `APN`
- **MCC/MNC settled — they DO exist on this build**, contrary to the
  original open question (they're absent from the *top* scroll position,
  which is what made them look missing at first; they appear once scrolled
  to the *middle* position). Real values observed, pre-filled:
  `mcc_field_label` = `MCC` (value seen: `440`, Japan), `mnc_field_label` =
  `MNC` (value seen: `11`, Rakuten Mobile — matches the "Rakuten SIM in a
  KDDI-branded unit" finding). **Do not delete these fields.**

### Not resolved (genuinely absent from available data — not guessed)
- `apn_settings.save_button_resource_id` — see "Highest priority" above.
- `apn_settings.add_button_resource_id` — the "+ add new APN" icon lives on
  the APN *list* screen, which was never captured (only the edit *form*, at
  3 scroll positions, was). There is nothing to find in current data; a
  list-screen dump is needed.
- `wifi_settings.password_field_resource_id` /
  `connect_button_resource_id` — the "Connect to network" dialog (shown
  after tapping an unsaved SSID) was never captured; only the network list
  screen was. Unchanged Stage A placeholders.

### Best-guess (marked `TODO(real-device, best-guess-standard-id)` in YAML —
standard AOSP/AndroidX framework ids, not app-specific, not invented to look
plausible; the dialog they belong to was never captured, only inferred)
- `apn_settings.dialog_edit_field_resource_id` = `android:id/edit`
- `apn_settings.dialog_confirm_button_resource_id` = `android:id/button1`

These matter because real captures revealed the APN edit form is a
**PreferenceScreen list**, not a set of inline EditTexts as Stage A assumed:
tapping a field row (by `field_row_resource_id` + label text) opens a small
edit dialog, and that dialog's own contents were never dumped. If either
best-guess id is wrong, `apn_setup.py`'s `_fill_labeled_field()` fails
cleanly (via `tap_resource_id()` returning False) rather than mistyping
into whatever happens to be focused — but field entry will not actually
work until confirmed.

### Wizard — hard constraint, not a temporary gap
No `uiautomator dump` exists or ever will for OOBE wizard screens on any of
the four models: factory reset wipes ADB authorization, and by the time ADB
is available again the wizard has already finished. Four separate remote
workarounds were tried on SHG10 and all failed (see docs/record.md for the
full list and the structural explanation). SHG10's wizard is instead driven
by visible text from the client's photographed reset session
(`docs/screens/shg10/wizard/`, 9 photos) — see
`config/models/sharp_aquos_sense7.yaml`'s `wizard:` block and
`src/phase2/wizard_walkthrough.py`'s screen-driven implementation.

Two button labels remain genuinely unverified (not legible in the client's
photos) and are marked `target_text: "TODO(verify-on-device)"` in the YAML
— deliberately a value that will never match anything real, so the wizard
fails loudly at that screen rather than guessing:
- `welcome` screen (「ようこそ」) — start button label unknown
- `software_update` screen (「ソフトウェア更新について」) — confirm button
  label unknown, SHARP-specific screen

**Open question for the client**: is 「オフラインで設定」 (offline setup) the
standard path for all devices? The client's photographed session took this
path and Google account sign-in never appeared, which — if standard —
substantially narrows what the wizard needs to automate. Not yet confirmed
as the universal case.

**Judgment call — "wizard complete" detection**: there is no reliable
captured signal for "we've reached the home screen" (it varies by
launcher/wallpaper and was out of scope for a text/dump capture).
`wizard_walkthrough.py` instead treats successfully handling the *last*
configured screen (`aquos_notify` / 「AQUOS Homeの通知アクセス」) as
completion. This is a deliberate simplification — flagging it in case a
more reliable home-screen signal becomes available later (e.g. a stable
launcher package name via `adb shell dumpsys window` instead of a UI dump).

### Toggle-tap safety (fixed, not just data)
Real capture showed the Wi-Fi toggle is a plain `Switch` with a `checked`
attribute — Stage A's original code tapped it unconditionally every time,
which would have **turned Wi-Fi off** on any device where it was already on
(true in the captured dump). `wifi_setup.py` now checks `checked` via
`node_is_checked()` before deciding whether to tap. Not a data gap, but
recorded here since it was discovered through this real capture.

## SOG08 (Xperia Ace III), SOG07 (Xperia 10 IV), SHG07 (AQUOS sense6s) —
## entirely untouched, out of scope for this pass

Per the Stage B task's explicit scope, these three still carry 100% of
their original Stage A placeholders — every `wizard_steps[*].resource_id`,
`wifi_settings.*`, and `apn_settings.*` value remains an invented
placeholder with a `TODO(real-device)` marker. No captures exist for any of
them (Wi-Fi, APN, or wizard). Same wizard constraint applies (no dump will
ever be possible) — they'll need the same photograph-derived, screen-driven
approach as SHG10 once reset sessions are done for them, plus real Wi-Fi/APN
dumps captured the same way as SHG10's were.

Package-name assumptions are a bigger open question for the two SHARP
models (SHG07, and previously SHG10 before its real data came in) than for
the two Sony models — SHG10's real data showed the Settings/Phone app
package names (`com.android.settings`, `com.android.phone`) were actually
right, but the *setup-wizard* package assumption was moot (text-matching
replaced it entirely) and SHARP-specific screens turned out to need
SHARP-specific handling regardless of package name. Don't assume SHG07 will
behave identically to SHG10 just because both are SHARP/AQUOS — confirm
independently.

## Schema additions beyond the original task prompt's illustrative example

Stage A already added 6 fields beyond the prompt's illustrative schema
(`wifi_settings.password_field_resource_id`,
`wifi_settings.connect_button_resource_id`,
`apn_settings.add_button_resource_id`, `apn_settings.mcc_field_resource_id`,
`apn_settings.mnc_field_resource_id`) because the specified function
signatures needed somewhere to put that data. Stage B adds more, all driven
by what real captures actually showed rather than by further guessing:

- `wifi_settings.menu_path`, `apn_settings.menu_path` steps can now be
  `{"type": "text"|"resource_id"|"content_desc", "value": "..."}` (or a bare
  string, still supported, for menu_path lists — the shape legacy models
  keep using) — needed once real data showed some navigation steps are
  icons with a resource-id (the APN gear icon) rather than text menu items.
- `apn_settings.field_row_resource_id` + `*_field_label` — replaces the
  literal-resource-id-per-field assumption for any model where real data
  shows fields don't have dedicated ids (confirmed true for SHG10; unknown
  for the other 3 until their own dumps exist).
- `apn_settings.dialog_edit_field_resource_id` /
  `dialog_confirm_button_resource_id` — the per-field edit dialog's own
  best-guess ids (see "Best-guess" above).
- `apn_settings.save_action_candidates` — informational only, not wired
  into any code path; records what was found for the Save-action question
  without guessing which (if either) actually works.
- `ui_automator.py` gained `find_by_content_desc`/`tap_by_content_desc`
  (icon-only controls have neither resource-id nor text — real captures
  showed at least 3 of these: APN's overflow menu, its "navigate up" arrow,
  and — per docs/record.md — the wizard's "+"-style add-new-APN icon whose
  screen was never captured), `node_is_checked` (toggle/switch state),
  `scroll_down` + `wait_for_text_to_disappear` (wizard spinner/scroll
  screens), and a `HazardousScreenError` guard (see below).

## Safety guard added (Stage B Task 4)

A live notification — 「USBデバッグが接続されました — 無効にするにはここを
タップしてください」 (USB debugging connected — tap here to disable) — sits
in the notification shade during automation on SHG10 (docs/record.md).
Confirmed only by direct observation during a live session, not a captured
dump (its exact bounds are unknown). `ui_automator.py` now refuses to tap
*anything* on a screen whose dump contains this text at all (rather than
computing an exclusion zone from bounds we don't have) — see
`HazardousScreenError`, `tests/test_ui_automator.py`'s hazard tests. This
is a whole-screen refusal, deliberately conservative; it hasn't been tested
against a real capture of the notification itself, only against the
transcribed text.

## Practical note: non-ASCII log output on Windows

`wizard_walkthrough.py`/`apn_setup.py` now log Japanese text (screen names,
labels) at INFO/ERROR level. On a Windows console using a non-UTF-8
codepage (the default, `cp1252`, on an English-locale Windows install),
`logging`'s console `StreamHandler` will hit `UnicodeEncodeError` on these
lines — caught internally by the logging module (won't crash the run) but
noisy, and the message is lost from the console (still captured correctly
in the log *file*, since `main_phase2.py`'s `FileHandler` is explicit
UTF-8). Run `chcp 65001` before starting a session on the real client PC's
console if clean on-screen Japanese log output matters there.
