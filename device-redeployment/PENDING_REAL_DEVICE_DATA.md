# Pending Real-Device Data

Tracks every placeholder value and open assumption still needing real-device
confirmation, so work can resume cleanly without re-deriving what's
outstanding. See `docs/record.md` for the full session notes (test logs,
navigation paths, capture methodology, judgment calls) behind every entry
here — this file is the checklist; that one is the evidence.

**Status as of 2026-09-11 (Stage B, ongoing):** **Wi-Fi connects
end-to-end on real hardware** — confirmed by a client screenshot showing
`earth5_1` / 接続済み (Connected), WPA3-Personal, 5GHz. **APN navigation,
the "+" add-button, and field entry through MNC are now confirmed working
on real hardware** (client run, 2026-09-11, after the screen-recognition +
add-button fixes below) — the remaining blocker is still the save step:
a client-supplied "before"/"after" dump pair
(`apn_failure_setting_SHG10.xml` / `apn_success_setting_SHG10.xml`)
confirmed the failing run produces **zero new APN entries** (the failure
dump is byte-identical to the pristine empty list), not a malformed one —
whatever blocks it does so before any entry is ever created. **Two fixes
are in place, not yet re-verified against a run made with both applied
together**:
1. MCC/MNC full-width digit entry (client's direct observation) — fixed
   via `input_digits_direct()`.
2. A defensive guard against `config/network.yaml` silently falling back
   to placeholder example data — added after the success dump revealed a
   real leftover APN entry literally named "<APN value from client>" on
   the device from some earlier run.
See "Highest priority" below — it is not yet confirmed whether fix #1
alone resolves the save failure; the exact terminal log from a run with
both fixes applied is still the single most useful missing piece. SHG10's
wizard is on a photograph-derived, text-matching config — real dumps for
the wizard are **not obtainable on any model, ever** (structural
ADB/factory-reset constraint, see docs/record.md). **SOG08, SOG07, and
SHG07 are entirely untouched** — still 100% Stage A placeholders, not
started.

## Highest priority

### Re-verify against real hardware with BOTH the digit-entry fix and the config-safety guard (2026-09-11, latest)

Not yet re-verified. Client supplied a "before"/"after" dump pair for a
run that still failed to save:
`tests/fixtures/apn_failure_setting_SHG10.xml` (after tapping 保存, still
landed here) is **byte-identical** to `apn_restricted_SHG10.xml` (the
pristine, zero-entries list) — confirming the save genuinely produces no
new entry at all, consistent with a validation dialog blocking it (same
conclusion as before, now with direct dump evidence instead of just a
description). It's unconfirmed whether this specific failing run already
included the MCC/MNC full-width-digit fix from immediately before this
entry — if not, that fix (still itself unverified against a live run)
may already resolve this.

The paired `apn_success_setting_SHG10.xml` (client's own manual save, for
comparison) also revealed something unrelated but worth fixing regardless:
a **second, older APN entry on the same device, literally named "<APN
value from client>"** — the exact placeholder string from
`config/network.yaml.example`. Real proof that an earlier run (at some
point, not necessarily recent) silently fell back to that example file
instead of a real `config/network.yaml` and created a garbage entry on
real hardware without erroring. Fixed: `main_phase2.py`'s
`_load_network_config()` now refuses to run at all — raises
`NetworkConfigError` — if `config/network.yaml` is missing, or if any
value in it still matches one of the example file's known placeholder
strings verbatim. This is unrelated to why *this* save failed (that
leftover entry is unchecked/inactive, a different entry from the one
being tested), but a real, concrete safety gap regardless.

**Next run should have both fixes in place** (this commit plus the prior
digit-entry one) — if it still doesn't save, the exact terminal log
output remains the one thing that would settle this for real, since dumps
of the failure state (now captured twice) show nothing more than "no
entry got created," not *why*.

### Re-verify against real hardware after switching MCC/MNC to keyevent digit entry (2026-09-11)

Not yet re-verified. Client directly reported the concrete, observable
cause of "typed through MNC but never saves": MCC/MNC were being entered
using FULL-WIDTH digits (e.g. "４４０") instead of half-width/ASCII
("440"). This device's on-device validation almost certainly checks for
ASCII digits specifically ("MCC欄は3桁で指定してください" — a full-width
"４４０" is a different Unicode range, U+FF10-FF19, not U+0030-U+0039, so
depending on exactly how the validation regex is written it may not even
register as digits at all) — this would explain the entry consistently
failing to save even though field-filling itself completed with no
errors, exactly as the client described.

Root cause of the full-width conversion itself: `input_text_direct()`
("input text") is meant to bypass the active IME entirely, but real
evidence now shows it doesn't fully do so for digits on this device —
plausibly the Japanese IME's zenkaku/hankaku conversion still intercepts
committed text. Fix: added `input_digits_direct()`
(`src/device/ui_automator.py`), which sends each digit as an individual
`adb shell input keyevent KEYCODE_N` — a different injection path that
maps directly to the physical/virtual number-row keys and isn't expected
to go through the same IME conversion. `_fill_labeled_field()` now uses
this for MCC/MNC specifically (`numeric_only=True`), while 名前/APN keep
using `input_text_direct()` as before (arbitrary text, not just digits).

**This is the client's own direct, concrete observation, not another
inferred hypothesis** — significantly higher confidence than the
confirm-button theory that was just ruled out. Still, "digits render
correctly now" and "the entry actually saves" are two different things to
confirm — watch closely on the next run, and if it still doesn't save,
the next need is still the same: the exact terminal log output, since a
validation dialog's real message (already logged by `_save_apn()`) would
immediately say whether this was the whole story or one of several
issues.

### Root cause of "not saving" ruled out: confirm-button hypothesis (2026-09-11)

An earlier hypothesis — that a wrong best-guess id for the per-field
dialog's confirm button was leaving each field's dialog stuck open — was
ruled out by a real dump of that dialog itself, captured while open
(`tests/fixtures/apn_accesshost_okbtn_SHG10.xml`): both
`dialog_edit_field_resource_id` ("android:id/edit") and
`dialog_confirm_button_resource_id` ("android:id/button1", confirmed to
genuinely be the "OK" button, not "キャンセル"/button2) were exactly right
all along — see "Resolved — per-field entry dialog" below. The defensive
hardening added for that hypothesis (hard failure instead of a silent
warning when either dialog tap isn't found) is kept regardless, since
it's correct practice, but it isn't the fix for "not saving" — see the
full-width-digits entry above for what is.

Two client-supplied real dumps from this same investigation
(`apn_accesshost_SHG10.xml`, `apn_accesshost_save_SHG10.xml`) turned out
to be byte-identical to already-captured/already-correctly-handled
fixtures (the edit form and the overflow "⋮"/"保存" popup) — they confirm
those two structures are right, not a source of new information.

### Re-verify against real hardware after the APN screen-recognition + add-button fixes (2026-09-11) — CONFIRMED WORKING

Two related fixes, both backed by a real dump
(`tests/fixtures/apn_restricted_SHG10.xml`) rather than a screenshot-only
guess, **now confirmed working by a live client run** (2026-09-11 — the
run got through navigation, the "+" tap, and all four fields before
stalling at save, per the entry above):

1. **Screen recognition.** A real run's log showed
   `android.settings.APN_SETTINGS` repeatedly reporting "didn't land on a
   recognizable APN list screen" even though it *was* landing correctly —
   `_looks_like_apn_list_screen()` only recognized the SHARP-skinned title
   (`content-desc` "アクセスポイント名"), not this device's actual
   intent-landing screen, whose title is `content-desc` "APN" on
   `com.android.settings:id/collapsing_toolbar" (confirmed by the dump —
   an earlier attempt at this fix guessed it was a plain `text` node
   instead, based on a screenshot; that would never have matched). Now
   accepts either content-desc title variant.
2. **Add-button.** The same dump also captured the "+" button itself: it
   has a real, unambiguous content-desc, `"新しい APN"` ("New APN"),
   sitting immediately left of the confirmed "⋮" overflow icon.
   `configure_apn()` now taps it directly via this content-desc — this
   *replaces* the position-estimate fallback (`tap_left_of_content_desc()`)
   for SHG10 specifically; that fallback remains in the code for any
   model/screen where no real identifier is captured yet.

### Re-verify against real hardware after the APN navigation root-cause fix

Not yet re-verified — this is the fix most likely to finally get a full
run through end-to-end. Every "apn menu navigation failed" error in prior
real runs traced to one bug: `menu_path`'s final step tried to
`tap_by_text()` on 「アクセスポイント名」, but hand-testing (2026-09-08/09)
confirmed that string is the *destination screen's own title* (rendered
via `content-desc` on the toolbar, same pattern as the edit form's
「アクセスポイントの編集」) — never a `text` node to tap. There was nothing
there to find; no id was ever going to fix it. Replaced with
`adb shell am start -a android.settings.APN_SETTINGS`, hand-confirmed to
reach the APN list in one step — tried first, with the (now-corrected)
`menu_path` kept only as a fallback. Also fixed in the same pass: MCC/MNC
row lookup now scrolls once and retries if the row isn't immediately
found (real confirmation they're below the fold, not just theoretically
possible), and `_save_apn()` makes a soft positive check for the new
entry reappearing on the list post-save (logged only, never a hard
failure on its own). See docs/record.md for the full account.

### Re-verify against real hardware after the destructive-tap safety fix

Also not yet re-verified. A real run's retry loop (Wi-Fi succeeds, a later
step fails, the whole flow retries from the top) showed `connect_wifi()`
re-running its full UI flow even though the device was already connected
— tapping the SSID's row opened "Network Details" (already-connected
state) instead of the join dialog the code assumed, and with no password
field actually present to focus, the password got typed as raw keystrokes
into whatever had default focus. The client caught it via screen-share:
repeated taps landing on **削除** (Forget) — which would have deleted the
just-established connection. Fixed: `connect_wifi()` now checks connection
state first and touches nothing at all if already connected; `削除`/
`接続を解除` also added to the permanent do-not-tap list as defense in
depth. **Next real run is what confirms this is actually closed** — test
the retry path specifically (e.g. let APN fail once on purpose, or just
run it twice in a row) so this scenario is provably exercised, not just no
longer reachable.

### Re-verify against real hardware after the dump_ui() pull-failure fix

Also not yet re-verified. A real run got through Wi-Fi and into APN menu
navigation, then crashed with a raw `FileNotFoundError` from
`ui_automator.dump_ui()` never checking whether its `pull()` call actually
succeeded — fixed with a clear error + automatic retry (uiautomator dump
is known to intermittently fail right after a screen transition, which is
exactly what had just happened).

### Wi-Fi scan results vary run to run at this location

Not a bug, just worth remembering: a real client-PC scan (2026-09-08)
showed the device's in-range networks were, at that moment, different from
both `wifi_list_SHG10.xml`'s original capture and from `earth5_1`
(`cityroam`, `JBCshoji`, `GatewayIkebukuro5fWifi1`, `USPOT_7407541_2.4G`,
`FREE_Wi-Fi_and_TOKYO`, `USPOT02_MESH_132119436_001`, `rv440m-34a2c1-1/-2`,
`iPhone`) — a "not found in scanned list" result doesn't automatically mean
the credentials are wrong.

**Wi-Fi passwords cannot be extracted via adb, ever, on a non-rooted
device** (confirmed: the shell user lacks the wifi permissions needed even
to reconnect a saved network — same `SecurityException` blocks
`cmd wifi connect-network` entirely, and reading `WifiConfigStore.xml`
needs root) — noted here in case a *different* network needs credentials
later; real ones are already in hand for `earth5_1`.

### Two wizard button labels — still the only wizard gap

`welcome` and `software_update` screens' button text remain illegible in
the client's photos (glare on one, cropped at the frame edge on the other)
— confirmed by a second independent review of all 19 photos, not just the
original transcription. One new observation: the `welcome` screen's button
may be icon-only (no text at all), which would mean the fix isn't just
"read the label" but potentially switching that one screen's action to
`tap_by_content_desc`. Needs a live look or a fresh photo during the next
factory reset.

### SOG08 / SOG07 / SHG07 — no real data of any kind yet

Same Wi-Fi list + APN dump process used for SHG10 hasn't been run for any
of the other three models. Highest-value next step once SHG10's remaining
gaps are closed.

## SHG10 (AQUOS sense7, SHARP/KDDI, Android 14) — Stage B, most of the way there

**Corrected finding:** real `adb` identification reported Android 14
(`[SHARP] KDDI SHG10 (Android 14)`), not Android 12 as the original task
spec assumed. Config and tests now reflect 14.

### Resolved — Wi-Fi (`tests/fixtures/wifi_list_SHG10.xml`, plus live testing 2026-09-08)
- `wifi_settings.toggle_resource_id` = `android:id/switch_widget` (unambiguous,
  single match) — checked via `node_is_checked()` before tapping (see
  "Toggle-tap safety" below)
- `wifi_settings.network_list_resource_id` = `android:id/title` (generic,
  must be paired with `text=<SSID>`)
- `wifi_settings.menu_path`: 設定 → ネットワークとインターネット →
  Wi-Fi とモバイルネットワーク — and as of 2026-09-08, `wifi_setup.py` tries
  `android.settings.WIFI_SETTINGS` first (confirmed working on real
  hardware: reaches the screen regardless of starting point, including from
  a bare home screen via `--skip-wizard`), falling back to this menu_path
  only if that intent doesn't land correctly
- `wifi_settings.connect_button_text` = `接続` (real — confirmed via
  screenshot, not a dump) — join-network dialog buttons are plain text
  (`キャンセル`/`接続`), tried before the still-unresolved
  `connect_button_resource_id` placeholder
- **Password entry mechanism**: real testing found `inject_text()` (ADB
  Keyboard broadcast) silently does nothing on this device — switched to
  `input_text_direct()` (`adb shell input text`); see "Resolved — text
  input mechanism" below
- **End-to-end connection confirmed on real hardware** (2026-09-08):
  `earth5_1` / 接続済み, WPA3-Personal, 5GHz — the full chain (shell attempt
  fails as expected → UI fallback → intent navigation → SSID tap → toggle
  check → password entry → connect tap → `dumpsys wifi` poll confirms) all
  worked together against a real network

### Resolved — APN navigation & fields (`tests/fixtures/apn_entry_{top,middle,bottom,filled}_SHG10.xml`, `apn_restricted_SHG10.xml`)
- **Navigation, primary path (real, hand-confirmed 2026-09-08/09, screen
  title confirmed by dump 2026-09-11):** `adb shell am start -a
  android.settings.APN_SETTINGS` reaches the APN list screen in one step.
  `apn_setup.py` tries this first, verifying landing via
  `_looks_like_apn_list_screen()`, which accepts **either** real title
  variant, both rendered via `content-desc` on the toolbar (never a plain
  `text` node — same pattern as the edit form's title): `アクセスポイント名`
  (the SHARP-skinned screen reached via manual `menu_path` navigation) or
  `APN` (the stock/AOSP-style screen this device's `APN_SETTINGS` intent
  actually lands on — confirmed by `apn_restricted_SHG10.xml`,
  resource-id `com.android.settings:id/collapsing_toolbar`; only the first
  variant was recognized before this, causing false "didn't land
  correctly" fallbacks). Not yet re-verified end-to-end against real
  hardware — see "Highest priority" above.
- **Navigation, fallback `menu_path`** (only used if the intent fails or
  doesn't land correctly): same as Wi-Fi's, then the gear icon
  (`com.android.settings:id/settings_button` — real, unambiguous
  resource-id). **Correctly ends at the gear icon** — an earlier version of
  this file had it continue to `tap_by_text()` on `アクセスポイント名`, which
  was a confirmed bug: that string is the destination screen's own title
  (rendered via `content-desc` on the toolbar, not a `text` node), so that
  step could never find anything to tap. This was the actual root cause of
  every "apn menu navigation failed" seen in real runs before this fix —
  not a wrong id, a step that never had a valid target at all.
- `apn_settings.field_row_resource_id` = `android:id/title` (generic, shared
  by every field on the edit form — 名前/APN/プロキシ/ポート/ユーザー名/
  パスワード/サーバー/MMSC/MMSプロキシ/MMSポート/MCC/MNC/認証タイプ/APNタイプ/
  APNプロトコル/APNローミングプロトコル/ベアラー/MVNOの種類/MVNO値 all share it)
- `apn_settings.name_field_label` = `名前`, `apn_field_label` = `APN`
- **MCC/MNC confirmed mandatory, not optional** (real on-device validation,
  2026-09-08 — supersedes the earlier "might be absent" note, which was
  wrong: they're just further down the scrollable form than first assumed).
  `mcc_field_label` = `MCC` (real value seen: `440`, Japan), `mnc_field_label`
  = `MNC` (real value seen: `11`, Rakuten Mobile). The device itself
  validates format (MCC exactly 3 digits, MNC 2 or 3) and refuses to save
  otherwise — `apn_setup.py` checks the same constraint before ever
  touching the device (`_MCC_PATTERN`/`_MNC_PATTERN`).
- **MCC/MNC rows confirmed below the fold** (real, 2026-09-08/09) — the
  field-row lookup now scrolls once and retries if a row isn't immediately
  found, same pattern as the wizard's `scroll_then_tap_by_text`.
- **Success state confirmed** (real, 2026-09-08/09): a successful save
  shows the new entry back on the APN list with its `名前` value as the
  first line (e.g. "TEST_SAVE_A / test.apn"). `_save_apn()` makes a soft,
  best-effort positive check for this now (logged only — info if found,
  warning if not — never turned into a failure on its own, since e.g. list
  scroll position could make it miss a genuinely successful save the
  validation-dialog check already accepted).
- **`apn_settings.add_button_content_desc` = `新しい APN`** ("New APN") —
  the "+ add new APN" icon, resolved from a real dump
  (`apn_restricted_SHG10.xml`, 2026-09-11) of the APN *list* screen itself
  (the missing piece before this — only the edit *form* had ever been
  captured). Has no resource-id at all on this build (confirmed by the same
  dump, not just absent data — `add_button_resource_id` stays `null`
  permanently). Sits immediately left of the confirmed "⋮" overflow icon,
  same height, sharing the exact x=969 edge — this also retroactively
  confirms the 2026-09-08/09 position-estimate fallback
  (`tap_left_of_content_desc()`) would have landed within ~11px of the
  real center, though it's no longer needed for this model now that the
  real value is known. `configure_apn()` prefers this content-desc over
  both `add_button_resource_id` and the position-estimate fallback. **Not
  yet confirmed against a live run** (the dump proves what's on screen, not
  that tapping it produces the expected next screen).

### Resolved — Save flow (real, confirmed on-device 2026-09-08 — see
`tests/fixtures/apn_overflow_menu_SHG10.xml`,
`apn_mcc_validation_SHG10.xml`, `apn_mnc_validation_SHG10.xml`,
`apn_entry_filled_SHG10.xml`)

This was the previous highest-priority blocker — now closed:
- Save is **two taps**, not one: open the overflow "⋮" menu
  (`overflow_menu_content_desc` = `その他のオプション` — content-desc only,
  no resource-id, confirmed across three separate captures now), then tap
  `保存` inside it (`save_menu_item_text` — shares `android:id/title` with
  the menu's other item, `キャンセル`, disambiguated by text, same pattern
  as everywhere else on this screen).
- The two earlier unconfirmed candidates are **resolved**: the overflow
  menu was the right one; `上へ移動` (navigate-up) was never actually the
  save trigger on this build — don't use it, `apn_settings.yaml` no longer
  references it.
- **Validation is sequential and blocking**: saving with any required field
  empty/invalid shows a modal `AlertDialog` instead of returning to the APN
  list, and does not save. Real messages, verbatim: `APNは必ず指定してください。`
  (APN empty), `MCC欄は3桁で指定してください。`, `MNC欄は2桁か3桁で指定してください。`
  Each is a standard AOSP dialog: message at `android:id/message`, single OK
  at `android:id/button1`. `apn_setup.py._save_apn()` checks for
  `android:id/message` after tapping `保存`; if present, logs the real
  message and fails loudly — **does not tap OK and retry blindly**, since a
  silent failure here would leave a device with no APN configured and no
  error surfaced.
- This also **indirectly confirms** the earlier best-guess
  `dialog_confirm_button_resource_id = "android:id/button1"` — real evidence
  now exists that this id is genuinely SHG10's standard AlertDialog
  positive-button id (from the validation dialog), raising confidence
  (though still not directly proven) that the same id is correct for the
  per-field entry dialog's own confirm button too.

### Resolved — text input mechanism (broadened three times, all from real evidence)
First finding: the device's default IME is Japanese kana mode, and the
on-screen keyboard can't reach digits without an explicit mode switch that
UI automation has no reliable way to trigger — `input_text_direct()`
(Android's built-in `adb shell input text`, bypassing the IME entirely)
fixed APN's MCC/MNC entry.

Second finding, same day: a live test of Wi-Fi password entry (SSID
`earth5_1`) showed the join-network dialog's password field stayed
**completely empty** after `wifi_setup.py` ran, with no errors logged —
`inject_text()`'s ADB Keyboard broadcast was silently going nowhere,
consistent with ADB Keyboard not actually being installed/set as the
active IME on this device (a prerequisite that was always manual/
unautomated — see README.md). Since `input_text_direct()` needs no extra
app and is already proven working on this device, both `wifi_setup.py`'s
password entry and **all four** of `apn_setup.py`'s labeled fields (not
just MCC/MNC) now use it — not because Name/APN specifically needed the
IME workaround, but because the ADB Keyboard path itself can't be trusted
on this device at all. `input_text_direct()`'s escaping was also hardened
at the same time (backslash/quote/`$`/backtick, not just spaces) since
passwords are far more likely than "440" to contain shell-special
characters.

Third finding, 2026-09-11: client directly observed `input_text_direct()`
("input text") committing MCC/MNC as **full-width digits** (４４０)
instead of half-width/ASCII (440) — apparently `input text`, despite being
meant to bypass the IME, still picks up this device's Japanese-IME
zenkaku conversion for digits specifically. New primitive,
`input_digits_direct()` (per-digit `adb shell input keyevent KEYCODE_N`),
routes around it — MCC/MNC use this now; 名前/APN (arbitrary text) keep
using `input_text_direct()`. This is the client's own direct observation
of the actual bytes typed, not an inference — see "Highest priority"
above for the theory of why this explains "typed through MNC but never
saves": the device's own MCC/MNC digit-count validation likely doesn't
recognize full-width digits as digits at all.

Legacy-shape models (the 3 untouched by Stage B) still default to
`inject_text()` — this finding is specific to this real device, not
generalized to models with no data of their own yet.

### Not resolved (genuinely absent from available data — not guessed)
- `wifi_settings.password_field_resource_id` / `connect_button_resource_id`
  — the "Connect to network" dialog (shown after tapping an unsaved SSID)
  was never captured; only the network list screen was. Unchanged Stage A
  placeholders. Also structurally can't ever contain the *value* of a saved
  password (see "Real Wi-Fi credentials" above) — this is about the
  dialog's field/button *ids*, a separate and solvable gap.

### Resolved — per-field entry dialog (`tests/fixtures/apn_accesshost_okbtn_SHG10.xml`, 2026-09-11)
- `apn_settings.dialog_edit_field_resource_id` = `android:id/edit` and
  `dialog_confirm_button_resource_id` = `android:id/button1` — previously
  only best-guess standard-framework ids (inferred from the
  *validation-error* dialog, never captured from this dialog directly).
  **Now directly confirmed**: a real dump of the per-field dialog itself,
  captured while open (mid-edit on 名前, before confirming), shows a plain
  standard AOSP AlertDialog — title at
  `com.android.settings:id/alertTitle` ("名前"), EditText at
  `android:id/edit` (focused, as expected), and two buttons: "OK" at
  `android:id/button1` and "キャンセル" (Cancel) at `android:id/button2`.
  The guess was exactly right on every point, including which of the two
  buttons is genuinely OK. This **rules out** the leading hypothesis for
  why a real 2026-09-11 run typed all four fields but the entry never
  saved — see "Highest priority" above for what's still actually unknown.

### Toggle-tap safety (fixed, not just data)
Real capture showed the Wi-Fi toggle is a plain `Switch` with a `checked`
attribute — Stage A's original code tapped it unconditionally every time,
which would have **turned Wi-Fi off** on any device where it was already on
(true in the captured dump). `wifi_setup.py` now checks `checked` via
`node_is_checked()` before deciding whether to tap.

### Network-config placeholder safety (fixed, not just data — 2026-09-11)
`main_phase2.py._load_network_config()` used to silently fall back to
`config/network.yaml.example`'s placeholder values (just a warning) if
`config/network.yaml` didn't exist. Real proof this is a genuine hazard,
not theoretical: `tests/fixtures/apn_success_setting_SHG10.xml` (a real
dump) shows a leftover APN entry on the device literally named "<APN
value from client>" — the example file's exact placeholder text, from
some earlier run that took this fallback path. There is no dry-run mode
(`main_phase2.py` always runs against real hardware), so this is now a
hard failure: `NetworkConfigError` if the file is missing, and the same
if any value inside it still matches a known placeholder string verbatim
(`_PLACEHOLDER_VALUES`) — catches both "never copied the example" and
"copied it but forgot to fill in one field."

### Wizard — hard constraint, not a temporary gap
No `uiautomator dump` exists or ever will for OOBE wizard screens on any of
the four models: factory reset wipes ADB authorization, and by the time ADB
is available again the wizard has already finished. Four separate remote
workarounds were tried on SHG10 and all failed (see docs/record.md for the
full list and the structural explanation). SHG10's wizard is instead driven
by visible text from the client's photographed reset session — see
`config/models/sharp_aquos_sense7.yaml`'s `wizard:` block and
`src/phase2/wizard_walkthrough.py`'s screen-driven implementation.

Two button labels remain genuinely unverified — see "Highest priority" above.

**Open question for the client**: is 「オフラインで設定」 (offline setup) the
standard path for all devices? The client's photographed session took this
path and Google account sign-in never appeared, which — if standard —
substantially narrows what the wizard needs to automate. Not yet confirmed
as the universal case.

**Judgment call — "wizard complete" detection**: there is no reliable
captured signal for "we've reached the home screen" (it varies by
launcher/wallpaper). A real `--skip-wizard` run (2026-09-08) landed on an
actual home screen and its dump (greeting widget, date widget, app icons)
confirms this variability firsthand — nothing in it would generalize as a
stable detector. `wizard_walkthrough.py` instead treats successfully
handling the *last* configured screen (`aquos_notify` /
「AQUOS Homeの通知アクセス」) as completion. Deliberate simplification, not
an oversight.

### `--skip-wizard` / `--skip-wifi` testing flags (infrastructure, not device data)
`--skip-wizard` added 2026-09-08 after discovering the SHG10 test unit was
already provisioned from an earlier session (landed on the home screen
instead of any wizard screen). Bypasses `run_wizard()` entirely for manual
testing against an already-provisioned device. Deliberately **not**
exposed on `run_phase2_batch()` (the production batch path) — only
`Slot.run_init_apn()` and `scheduler.run_slot_with_retries()` accept it,
both requiring an explicit, per-call opt-in. (`--skip-wifi` was proposed
the same day, same pattern, but wasn't ultimately needed once Wi-Fi
started working — not wired up.)

### `dump_ui()` retry on transient pull failure (infrastructure, not device data)
Added 2026-09-08 after a real crash: `uiautomator dump`'s pull is known to
intermittently fail right after a screen transition, and `dump_ui()` never
checked `client.pull()`'s return value — a failed pull crashed with a raw
`FileNotFoundError` from reading a file that was never written. Now raises
a clear `AdbCommandError` and retries up to 3 times (1s delay) before
giving up. Fixed in the shared `dump_ui()`, so it protects every
tap/find call across wizard, Wi-Fi, and APN — not specific to where it
happened to first surface (APN menu navigation).

## SOG08 (Xperia Ace III), SOG07 (Xperia 10 IV), SHG07 (AQUOS sense6s) —
## entirely untouched, out of scope for this pass

Per the Stage B task's explicit scope, these three still carry 100% of
their original Stage A placeholders — every `wizard_steps[*].resource_id`,
`wifi_settings.*`, and `apn_settings.*` value remains an invented
placeholder with a `TODO(real-device)` marker. No captures exist for any of
them (Wi-Fi, APN, or wizard). Same wizard constraint applies (no dump will
ever be possible) — they'll need the same photograph-derived, screen-driven
approach as SHG10, plus real Wi-Fi/APN dumps captured the same way as
SHG10's were (Wi-Fi list, APN entry form at multiple scroll positions, APN
overflow menu, APN validation dialogs).

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
  ids, resolved (see "Resolved — per-field entry dialog" above).
- `apn_settings.overflow_menu_content_desc` / `save_menu_item_text` — the
  real, confirmed two-tap save flow (replaces the earlier
  `save_action_candidates` list, which recorded two unconfirmed guesses;
  one turned out right, one wrong — see "Resolved — Save flow" above).
- `ui_automator.py` gained `find_by_content_desc`/`tap_by_content_desc`
  (icon-only controls), `node_is_checked` (toggle/switch state),
  `get_node_text` (reading dialog/message content, not just detecting
  presence), `scroll_down` + `wait_for_text_to_disappear` (wizard
  spinner/scroll screens), `input_text_direct` (numeric field entry
  bypassing the IME), `tap_left_of_content_desc` (2026-09-11: estimates a
  same-width adjacent icon's position from a confirmed neighbor's real
  bounds — generic fallback for any icon-only control with no identifier
  of its own captured yet), and a `HazardousScreenError` guard (see below).
- `apn_settings.add_button_content_desc` (2026-09-11) — the "+ add new
  APN" icon's own content-desc, once real data showed it has one (unlike
  `add_button_resource_id`, which this icon genuinely lacks on this
  build). Takes priority over both `add_button_resource_id` and the
  `tap_left_of_content_desc()` fallback when set.

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

## Real-device bugs found and fixed (infrastructure, not device data)

- **`adb.platform_tools_path` misconfiguration**: it's a directory, but was
  being passed straight through as the `adb` executable path itself, so
  every `AdbClient` call failed with `OSError`, silently swallowed into a
  plain `False` by `is_connected()` — indistinguishable from a genuinely
  disconnected device. Fixed: `main_phase2._resolve_adb_path()` joins the
  directory with the executable name and verifies it exists;
  `AdbClient.is_connected()` now raises `AdbCommandError` instead of
  swallowing this class of failure into `False`.
- **UTF-8 decode crash**: `subprocess.run(..., text=True, ...)` decodes
  using the OS locale codepage (`cp932` on the client PC's Japanese-locale
  Windows) rather than UTF-8, which is what `adb`'s actual output uses.
  Real device output (`dumpsys wifi`, containing real Wi-Fi SSIDs) crashed
  a background thread inside `subprocess.run()` itself — invisible to any
  `try`/`except` in this codebase — leaving `stdout=None` and surfacing
  several calls later as a confusing `TypeError`. Fixed: explicit
  `encoding="utf-8", errors="replace"`.

Neither of these were device-data gaps — both were pure code bugs, found
only because real hardware surfaced conditions (a real Windows locale, real
non-ASCII device output) that the fake/mock ADB layer never exercised.
