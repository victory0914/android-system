# Pending Real-Device Data

Tracks every placeholder value and open assumption still needing real-device
confirmation, so work can resume cleanly without re-deriving what's
outstanding. See `docs/record.md` for the full session notes (test logs,
navigation paths, capture methodology, judgment calls) behind every entry
here — this file is the checklist; that one is the evidence.

**Status as of 2026-09-11 (Stage B): 🎉 SHG10's Phase 2 flow (Wi-Fi + APN)
is CONFIRMED WORKING end-to-end on real hardware.** Client run:
`SUCCESS: device 352063910272451 reached LOGIN_INSTALL` — Wi-Fi (already
connected, correctly detected and skipped), APN navigation, the "+" tap,
all four fields, and the save itself all completed successfully in one
real run, and the client independently confirmed by manually reopening
the APN list that `rakuten.jp` was genuinely saved and selected. This is
the first time the full chain has worked all the way through — every
"re-verify against real hardware" entry that used to be tracked here is
now confirmed (see "Resolved — full Phase 2 run confirmed end-to-end"
below for the complete account of what got this here).

One wrinkle, fixed same-day: the automation's own post-save soft check
warned `'rakuten.jp' wasn't spotted back on the APN list`, even though the
save had genuinely succeeded — the list can take a moment to actually
refresh after 保存, and the very next dump can still show the pre-save
state. Not a real failure (the check is soft — it never blocks success on
its own), but misleading. `_save_apn()` now retries the check once after
a short delay before giving up. See "Resolved" below.

SHG10's wizard is on a photograph-derived, text-matching config — real
dumps for the wizard are **not obtainable on any model, ever** (structural
ADB/factory-reset constraint, see docs/record.md); 2 of 9 screens' button
labels are still unverified (see "Highest priority" below). **SOG08,
SOG07, and SHG07 are entirely untouched** — still 100% Stage A
placeholders, not started — now the next real priority since SHG10 itself
is working.

## Highest priority

With SHG10's Wi-Fi + APN flow now confirmed working end to end, the two
remaining priorities are both further below (kept in their original
sections rather than duplicated here):

- **"Two wizard button labels — still the only wizard gap"** (under
  "SHG10 (AQUOS sense7...)" below) — now the main SHG10 gap: everything
  else is implemented and confirmed working. Resolving these (or
  accepting the risk and testing anyway) is what's needed to confirm a
  *complete* fresh-device flow (wizard + Wi-Fi + APN), not just Wi-Fi +
  APN with `--skip-wizard`.
- **"SOG08 / SOG07 / SHG07 — no real data of any kind yet"** (same
  section) — entirely untouched, still 100% Stage A placeholders. Now the
  next real priority for Stage B to expand to, if/when hardware for them
  becomes available.

### Re-verify the destructive-tap safety fix's retry path specifically

The single item from the old "re-verify" list not exercised by the
successful run above: `connect_wifi()`'s already-connected check was
exercised (it correctly detected `earth5_1` was already connected and did
nothing), but the specific *retry-after-a-later-step-fails* scenario the
original bug was found in (Wi-Fi succeeds, APN fails, the whole flow
retries from the top) hasn't been deliberately re-exercised since the
fix. Low urgency now — the underlying bug (connect_wifi() re-running its
full UI flow when already connected) is structurally fixed regardless of
which step triggers a retry — but worth a deliberate test (e.g. run twice
in a row) for full confidence.

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

## Resolved — full Phase 2 run confirmed end-to-end (2026-09-11)

Every fix below was previously tracked as "not yet re-verified against
real hardware" — a single successful client run confirmed all of them at
once, reaching `LOGIN_INSTALL`:

- **APN navigation root-cause fix**: `menu_path`'s old final step tried
  `tap_by_text()` on 「アクセスポイント名」, which was always the destination
  screen's own title (rendered via `content-desc`, never a `text` node) —
  there was nothing there to tap. Replaced with
  `adb shell am start -a android.settings.APN_SETTINGS` as the primary
  path, hand-confirmed to reach the APN list in one step; `menu_path` kept
  only as a fallback.
- **Screen-recognition fix**: `_looks_like_apn_list_screen()` initially
  only recognized the SHARP-skinned title (`content-desc`
  「アクセスポイント名」), not this device's actual intent-landing screen
  title (`content-desc` "APN" on `com.android.settings:id/collapsing_
  toolbar`). Now accepts either.
- **Add-button fix**: the "+" button has a real, unambiguous content-desc,
  `"新しい APN"`, confirmed by a real dump
  (`tests/fixtures/apn_restricted_SHG10.xml`) — tapped directly via that
  content-desc, no longer via the position-estimate fallback (which
  remains in the code for any model/screen without a captured identifier).
- **Per-field dialog ids confirmed real**, not just best-guessed:
  `dialog_edit_field_resource_id` ("android:id/edit") and
  `dialog_confirm_button_resource_id` ("android:id/button1") — confirmed
  by a real dump of the dialog itself, open
  (`tests/fixtures/apn_accesshost_okbtn_SHG10.xml`). This ruled out an
  earlier hypothesis (a wrong confirm-button id leaving dialogs stuck
  open) as the cause of a since-resolved save failure — the hardening
  added for that hypothesis (hard failure instead of a silent warning on
  either dialog tap) stays regardless, as correct defensive practice.
- **MCC/MNC full-width-digit fix** — the actual, client-observed root
  cause of "typed through MNC but never saves": MCC/MNC were being
  entered as full-width digits (４４０) instead of half-width/ASCII (440)
  via `input_text_direct()` ("input text"), which is meant to bypass the
  active IME but evidently didn't fully do so for digits on this device.
  New primitive `input_digits_direct()` sends each digit as its own
  `adb shell input keyevent KEYCODE_N` instead — `_fill_labeled_field()`
  uses this for MCC/MNC (`numeric_only=True`), 名前/APN keep using
  `input_text_direct()`.
- **Network-config placeholder guard**: `config/network.yaml.apn_name`
  turned out to still be the literal placeholder text `<APN value from
  client>` on the client's machine — meaning every real run before this
  one was attempting to save that exact string (spaces, angle brackets,
  and all) as the actual APN value, independently plausible as a
  contributor to every "not saving" symptom seen throughout this whole
  investigation. Not a code bug (the guard correctly caught it) — the
  client edited their own `config/network.yaml` to fix it. The guard
  itself was narrowed same-day after an unrelated false positive (see
  "Network-config placeholder safety" below).
- **Post-save soft-check retry**: the list can take a moment to refresh
  after 保存 — the check now retries once after a short delay before
  logging its "wasn't spotted" warning, avoiding a false-negative warning
  on a save that actually succeeded.
- **`dump_ui()` pull-failure fix**: a real run crashed with a raw
  `FileNotFoundError` from `dump_ui()` never checking whether its `pull()`
  call succeeded — fixed with a clear error + automatic retry.

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
  correctly" fallbacks). **Confirmed end-to-end on real hardware,
  2026-09-11** — see "Resolved — full Phase 2 run confirmed end-to-end"
  below.
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
  both `add_button_resource_id` and the position-estimate fallback.
  **Confirmed against a live run, 2026-09-11** — see "Resolved — full
  Phase 2 run confirmed end-to-end" below.

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

**Self-correction, same day:** the first version of the placeholder check
walked the *entire* config recursively, and immediately blocked a real
client run — `config/network.yaml`'s `apn.carrier` still had its
placeholder text, even though `carrier` is documentation-only and never
read by any code path (`src/orchestration/slot.py` only ever reads
`apn_name`/`mcc`/`mnc` and `wifi.ssid`/`wifi.password`). A real, correctly
filled-in config got refused over a field nothing depends on. Narrowed to
an explicit whitelist, `_REQUIRED_CONFIG_PATHS`, matching exactly what
`slot.py` consumes — `apn.carrier` (and any other future documentation-
only field) is intentionally never checked.

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
