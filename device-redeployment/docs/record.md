# Record

Living notes file for findings from real-device connection sessions that are
relevant to the `device-redeployment` code/config (YAML schemas, automation
tap paths, wizard detection, orchestration assumptions, etc.).

**How to add to this file:**
- If the device model already has a section below, add a new dated bullet
  under the relevant category heading (or add a new category heading if none
  fits).
- If it's a new model, copy the "Template for a new device section" block at
  the bottom and fill it in.
- Each finding should note *why it matters* (which file/behavior it affects),
  not just the raw observation.

---

## SHG10 (SHARP AQUOS sense7, KDDI branding, Android 14)

**Serial:** 352063910272451
**Confirmed identity string (from adb):** `[SHARP] KDDI SHG10 (Android 14)`

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| 2026-09-04 | USB/ADB detection | `adb devices` | Device recognized: `352063910272451 device` |
| 2026-09-04 | scrcpy connect, default H.264 encoder | `scrcpy --render-driver=software -s 352063910272451 --ignore-video-encoder-constraints` | Encoder crashed (`MediaCodec` `IllegalArgumentException`/`CodecException`) at every attempted resolution during automatic downsize retry (1920→1600→1280→1024→800); server process killed, window stayed black |
| 2026-09-04 | List device video/audio encoders | `scrcpy --list-encoders -s 352063910272451` | Hardware: H.264 (`c2.qti.avc.encoder`), H.265 (`c2.qti.hevc.encoder`). AV1/VP8/VP9 software-only. Audio (opus/aac/flac) all software-only |
| 2026-09-04 | scrcpy connect, H.265 encoder (1st run) | `scrcpy --video-codec=h265 -s 352063910272451` | Succeeded after 2 automatic downsize retries (1920→1600→1280→1024), reached `Texture: 354x800`; screen visible briefly then went black (device screen timeout, not an encoder failure) |
| 2026-09-04 | scrcpy connect, H.265 encoder (2nd run) | `scrcpy --video-codec=h265 -s 352063910272451` | Succeeded immediately, no retries, full native resolution `Texture: 852x1920`; stable live mirroring confirmed (home screen visible and interactive) |
| 2026-09-04 | Wake device from screen-off | `adb -s 352063910272451 shell input keyevent 26` | Screen woke to swipe-unlock (no PIN/pattern) |
| 2026-09-08 | scrcpy connect, default H.264, **after factory reset** | `scrcpy --render-driver=software -s 352063910272451` | Reached `Texture: 852x1920` after only 1 initial error — far better than pre-reset behavior. H.264 may be usable post-reset; single observation only, not yet reproduced |
| 2026-09-08 | Verify ADB auth restored after client re-enabled USB debugging | `adb devices` | `352063910272451 device` — client's re-authorization successful |
| 2026-09-08 | Keep screen awake while cabled | `adb -s ... shell svc power stayon usb` | Worked; screen no longer times out during sessions |
| 2026-09-08 | Restore provisioning flags + reboot after destabilization | `settings put secure user_setup_complete 1` / `put global device_provisioned 1` / `reboot` | Device recovered fully; both flags read back `1`, no crash dialog, nav bar normal |

**Conclusion for this unit:** `--video-codec=h265` is the safe default —
H.264 failed completely pre-reset. Post-reset H.264 worked once, suggesting
the failure may be state-dependent rather than purely a hardware-encoder bug,
but this is a single observation. Keep using h265 unless further evidence
accumulates.

### Carrier / SIM — relevant to `apn_setup.py`, `PENDING_REAL_DEVICE_DATA.md`
- *2026-09-04:* Lock screen displayed **"Rakuten"** as the active carrier, not
  au/KDDI, despite the KDDI model branding (SHG10).
- Implication: do not assume model branding (KDDI) implies KDDI APN defaults
  — the SIM actually installed per device in the farm may not match the
  model's carrier branding. Confirm actual SIM/carrier per device before
  applying any APN default.

### First-run wizard — relevant to `wizard_walkthrough.py`
- *2026-09-04 (initial guess — SUPERSEDED, see below):* Notification shade
  showed a persistent **「セットアップを完了させて」(Complete Setup)** banner.
  Initially assumed to be the OOBE wizard entry point.
- *2026-09-04 (CORRECTED):* Tapping that banner opened a **「楽しいアプリを発見
  しましょう」(Discover fun apps)** Play Store promo screen — skip top-right,
  「続行」bottom. This is a **post-setup nudge, not the real SetupWizard.**
  This unit had already completed its OOBE long before (home screen, installed
  apps, configured SIM all present).
- Conclusion: the genuine OOBE wizard screens (language → terms → Wi-Fi →
  account) exist **only** in the window between a factory reset and first
  reaching a home screen. They cannot be reached on an already-provisioned
  device. Real dumps for `wizard_walkthrough.py` require a reset.
- Also seen in the shade: **「最新Androidへようこそ!」** and **「画面ロックを
  設定・1日」** — the latter independently confirms no screen lock is set on
  this unit (see Lock state below).

### UI hazard — relevant to tap-path safety in automation
- *2026-09-04:* Notification shade also showed a live **「USBデバッグが接続さ
  れました — 無効にするにはここをタップ」(USB debugging connected — tap here
  to disable)** affordance.
- Hazard: any `tap_by_text` / coordinate-based tap near this must not hit it —
  doing so would disable USB debugging and kill adb access to that device
  mid-run. Worth an explicit exclusion/guard in the tap-path logic, or at
  least a regression test case.

### Lock state — relevant to `model_profile.py` / orchestration pre-checks
- *2026-09-04:* Waking the device (`input keyevent 26`) showed an
  open-padlock swipe icon, not a PIN/pattern pad — this unit unlocks without
  credentials.
- Independently corroborated by the 「画面ロックを設定」 notification still
  pending in the shade.
- Confirms (for at least this unit) the assumption that devices in the farm
  can be unlocked without credential entry. Worth verifying this holds across
  all four models before relying on it in orchestration.

### Wi-Fi network list — relevant to `wifi_setup.py`, `ui_automator.py`
- *2026-09-04:* Navigation path confirmed on this SHARP skin:
  **設定 → ネットワークとインターネット → Wi-Fi とモバイルネットワーク**.
  Wi-Fi toggle must be switched ON before the SSID list renders at all.
- Real SSIDs visible at the client site, including **near-duplicate pairs**:
  `ARIZASU-WiFi-6F_2.4GHz` / `ARIZASU-WiFi-6F_5G`, and
  `SPWH_L13_72E834` / `SPWH_L13_72E834_5G`. Others: `HR02b-BA15BA`,
  `earth2.4_6`, `earth5_1`.
- Implication: these are concrete real-world cases for the
  `AmbiguousResourceIdError` / text-disambiguation logic — replace the
  hypothetical example in `PENDING_REAL_DEVICE_DATA.md` with these.
- Note: the PC's own active network is `earth5_6` (Windows classifies it as
  a **Public** network — see Windows environment section below).
- *2026-09-08:* Client supplied real credentials for one of the above:
  `earth5_1` / `earth5_1` (SSID/password identical). Set in
  `config/network.yaml` (gitignored, local to the client PC).
- *2026-09-08:* First live test with real credentials — the shell path
  (`cmd wifi connect-network`) confirmed blocked by the same
  `SecurityException` as every prior attempt (shell user, uid 2000, lacks
  the wifi permission on this build). The UI fallback correctly navigated
  (`WIFI_SETTINGS` intent) and reached the real join-network dialog for
  `earth5_1` — but the password field stayed **completely empty**, no
  errors logged. Root cause: `inject_text()`'s ADB Keyboard broadcast was
  going nowhere — consistent with ADB Keyboard not actually being
  installed/set as the active IME on this device (always a manual,
  unautomated prerequisite — see README.md). Since `input_text_direct()`
  (`adb shell input text`) was already proven working on this same device
  for APN's MCC/MNC, switched Wi-Fi password entry to it too — see
  PENDING_REAL_DEVICE_DATA.md ("Resolved — text input mechanism") for the
  full writeup, which also covers broadening the same fix to APN's
  Name/APN fields (same device, same underlying dependency, so almost
  certainly the same silent failure waiting there too).
- *2026-09-08 (second live test, after the `input_text_direct()` fix):*
  Password entry now works — confirmed by the client screenshot showing
  「接続」/「キャンセル」 as the join-network dialog's two buttons. But
  `wifi_setup.py` still couldn't tap Connect: `connect_button_resource_id`
  was (like `password_field_resource_id`) an unconfirmed Stage A
  placeholder, and the tap's return value was never even checked. Fixed by
  adding `connect_button_text: "接続"` — plain text, same 保存/キャンセル
  pattern already proven for the APN save dialog — tried first, with the
  placeholder resource-id kept only as a secondary fallback.
- *2026-09-08 (third live test, after the connect-button fix):* **Wi-Fi
  connects end-to-end on real hardware** — client screenshot confirmed
  `earth5_1` / 接続済み (Connected), WPA3-Personal, 5GHz. First fully
  working Phase 2 step, real device to real network. (The connect-button
  tap only worked on the first of three attempts in that run — later
  retries saw a "connect button not found" warning, correctly: once
  already connected, the same network's row opens a "Network Details"
  screen instead of the join dialog, which has no 接続 button at all.)
- *2026-09-08 (fourth live test — safety issue, corrects the note above):*
  "Nothing to fix there" was wrong. On the retries where the device was
  already connected, the client caught the automation via screen-share
  repeatedly tapping near **削除** (Forget) on that Network Details screen —
  a live screenshot with the tap location visible confirmed it. Root
  cause: `connect_wifi()` never checked whether the device was already
  connected before running the whole UI flow. It tapped the SSID's row
  (landing on Network Details, not the join dialog), found no password
  field or 接続 button (both correctly logged as "not found"), but had
  already called `input_text_direct()` to type the password — with
  nothing actually focused as a text field on that screen, those
  keystrokes went to whatever had default focus instead, consistent with
  landing on 削除. Deleting the just-established connection would have
  been actively destructive, not just a wasted retry. Fixed:
  `connect_wifi()` now checks `_is_wifi_connected()` FIRST, before
  touching the UI (or even attempting the shell command) at all — if
  already connected, it returns immediately and touches nothing.
  `削除`/`接続を解除` also added to `ui_automator._NEVER_TAP_TEXT` as
  defense-in-depth (doesn't address this specific root cause, since
  `input_text_direct()` doesn't go through `tap_by_text()`'s guard, but
  costs nothing and blocks any future path that might target them
  explicitly).

### APN settings — relevant to `apn_setup.py`
- *2026-09-04:* Navigation path confirmed:
  **設定 → ネットワークとインターネット → Wi-Fi とモバイルネットワーク →
  (gear icon next to the carrier name "Rakuten") → アクセス ポイント名**.
  Note this is reached via a **gear icon**, not a text menu item.
- APN list screen shows existing entry `rakuten.jp` with a radio selector.
  The "add new APN" control is a **`+` icon in the top-right with no visible
  text label** — implication: `add_button_resource_id` cannot be resolved via
  `find_by_text`; it must use a resource-id.
- Entry form 「アクセスポイントの編集」 fields observed (top of form):
  名前 / APN / プロキシ / ポート / ユーザー名 / パスワード / サーバー / MMSC.
  **MCC/MNC not visible in the top portion** — unresolved whether they exist
  further down or are absent on this build.
- **No Save button visible on the form** — may live in the ⋮ overflow menu
  (top-right) or be triggered by the back arrow. Unresolved;
  `save_button_resource_id` still needs this answered.
- Separate finding: **「モバイル ネットワークへの接続」/ eSIM download screen**
  exists on this model (reached via SIM settings). This is NOT the APN entry
  screen — do not confuse the two when writing navigation paths.
- *2026-09-08 (SUPERSEDES the 2026-09-04 MCC/MNC note above):* MCC/MNC ARE
  present on this build — the earlier note was wrong, they're just further
  down the scrollable form than the initial look covered. Confirmed via
  `apn_entry_middle_SHG10.xml`, `apn_entry_bottom_SHG10.xml`, and now also
  `apn_entry_filled_SHG10.xml`. They are **mandatory**, not optional: the
  device's own save validation rejects an entry without them.
- *2026-09-08:* **APN save flow confirmed.** Save is NOT a button on the
  form — it's in the overflow "⋮" menu (content-desc `その他のオプション`,
  no resource-id — same icon-only pattern noted above for the "+" add
  control). Opening it shows two items sharing `android:id/title`: `保存`
  (Save) and `キャンセル` (Cancel) — same generic-id-plus-text-disambiguation
  pattern as the field rows and the Wi-Fi list. The earlier `上へ移動`
  (navigate-up) candidate was tested and is **not** the save trigger on
  this build — don't use it.
- *2026-09-08:* **Save validation is sequential and blocking.** Saving with
  a required field empty/invalid shows a modal `AlertDialog` and does NOT
  save — confirmed real messages, in the order they appear:
  `APNは必ず指定してください。` (APN field empty) →
  `MCC欄は3桁で指定してください。` (`apn_mcc_validation_SHG10.xml`) →
  `MNC欄は2桁か3桁で指定してください。` (`apn_mnc_validation_SHG10.xml`).
  Each dialog: message at `android:id/message`, single OK at
  `android:id/button1` — real confirmation that `button1` really is this
  build's standard AlertDialog positive-button id (raises confidence in
  the earlier best-guess for the per-field entry dialog's own confirm
  button, which uses the same assumption but is still not directly
  captured).
- *2026-09-08:* **Numeric field entry needs a different mechanism.** The
  device's default IME is Japanese kana mode; the on-screen keyboard can't
  reach digits for MCC/MNC without an explicit mode switch that UI
  automation has no reliable way to trigger. `adb shell input text "440"`
  (Android's built-in text-injection, bypassing the IME) works instead of
  the ADB Keyboard broadcast used for the other (alphanumeric) fields.
- Implication for all of the above: `apn_setup.py` was rewritten
  accordingly (`_save_apn()`, `_MCC_PATTERN`/`_MNC_PATTERN` pre-validation,
  `input_text_direct()` for MCC/MNC specifically) and
  `config/models/sharp_aquos_sense7.yaml` updated
  (`overflow_menu_content_desc`, `save_menu_item_text`). See
  `PENDING_REAL_DEVICE_DATA.md` for the full before/after.
- *2026-09-08/09 (root cause of "apn menu navigation failed"):* Hand-tested
  and confirmed `adb shell am start -a android.settings.APN_SETTINGS`
  reaches the APN list screen in a single step. This also explains — and
  fixes — every "apn menu navigation failed" error seen in prior real
  runs: `menu_path`'s final step tried `tap_by_text()` on
  「アクセスポイント名」, but that string is the *destination screen's own
  title*, rendered via `content-desc` on the toolbar (the exact same
  pattern already confirmed for the edit form's 「アクセスポイントの編集」)
  — never a `text` node at all. There was nothing there to tap; the bug
  wasn't a wrong id, it was a step that could never have succeeded.
  `menu_path` (kept as a fallback if the intent ever fails) now correctly
  ends at the gear icon instead.
- *2026-09-08/09:* **[+] add-new-APN button confirmed icon-only, top-right
  of the APN list**, matching the earlier finding — position confirmed by
  hand, but its resource-id still isn't (no dump of the APN *list* screen
  itself exists, only the edit *form* reached after tapping it/an existing
  entry). Still `null`/TODO in config.
- *2026-09-08/09:* **MCC/MNC rows confirmed below the fold** — scrolling is
  required to reach them, not just theoretically possible. `apn_setup.py`'s
  field-row lookup now tries once, scrolls once, and retries if the row
  isn't found — same `scroll_then_tap_by_text` pattern already used for the
  wizard's scrollable terms screen.
- *2026-09-08/09:* **Success state confirmed**: after a save with no
  validation dialog, the new entry reappears on the APN list with its
  `名前` value as the first line (e.g. "TEST_SAVE_A / test.apn" — name then
  APN string). `_save_apn()` now makes a soft, best-effort positive check
  for this (`find_by_text(ui_xml, apn_name)`) — logged only (info if found,
  warning if not), never turned into a failure on its own, since e.g. list
  scroll position could make this check miss a genuinely successful save
  the validation-dialog check already accepted.
- *2026-09-11 (real run — `_looks_like_apn_list_screen` was too narrow):*
  Client's log showed `android.settings.APN_SETTINGS` repeatedly logging
  "didn't land on a recognizable APN list screen; falling back to
  menu_path" followed by `apn menu navigation failed`, even though the
  intent *was* landing correctly. Root cause: the landing-check only
  accepted the SHARP-skinned title rendered via `content-desc`
  ("アクセスポイント名", the pattern confirmed 09-08/09 above) — but on
  this device the screen reached via the *intent* instead shows a different
  title, "APN", which the check didn't recognize at all.
  `_looks_like_apn_list_screen()` now accepts either title variant (at
  first fixed based on the client's screenshot alone, which read as a
  plain `text` heading — a real dump captured shortly after, see below,
  corrected this to `content-desc` too, same pattern as everywhere else on
  this screen). The same screenshot also showed a warning banner,
  「このユーザーはアクセスポイント名設定を利用できません」("this user
  cannot use APN name settings") — client confirmed by hand that this does
  **not** block the "+" button from working with a normal tap; it's just
  informational text on this screen, not an access restriction to route
  around.
- *2026-09-11 (client correction, [+] tap mechanism):* My first read of the
  client's screenshot/caption (mentioning "you must press the Tab key")
  was wrong — I initially built keyboard-focus-cycling (`KEYCODE_TAB`/
  `KEYCODE_ENTER`) on the theory the "+" button was touch-disabled. Client
  corrected this directly: "Tab" referred to the on-screen "+" icon itself
  (translation artifact), not a keyboard key — the intended flow is a
  normal tap on "+", then fill 名前/APN/MCC/MNC one at a time via the
  already-implemented per-row dialog mechanism, OK each one, then the
  already-implemented two-tap overflow→保存 save. The keyboard mechanism
  was fully reverted (no trace left in `ui_automator.py`).
- *2026-09-11:* **[+] add-new-APN button still has no captured id of its
  own** (still true from 09-08/09 above — no dump of the list screen with
  a known-empty/known-count APN set exists, only a hand photo). Rather than
  leave the tap silently skipped, `configure_apn()` now falls back to a new
  primitive, `tap_left_of_content_desc()`: it taps an ESTIMATED position
  immediately left of the confirmed "その他のオプション" (⋮ overflow menu)
  icon, assuming a same-width icon occupies that adjacent space with no
  gap — consistent with the real screenshot's layout (+ and ⋮ both
  top-right, adjacent). This is explicitly an estimate, not a confirmed
  value: if wrong, it fails loudly a few steps later (the expected field
  rows won't be found), never silently misfires into a different action.
  Needs real-hardware confirmation before `add_button_resource_id` can be
  marked resolved in `PENDING_REAL_DEVICE_DATA.md`.
- *2026-09-11 (same day, client attached a real dump — supersedes both
  entries above):* Client attached `tests/fixtures/apn_restricted_SHG10.xml`
  — the first-ever real `uiautomator dump` of the APN *list* screen itself
  (every prior APN capture was the edit *form*, reached after tapping an
  entry). This settles both open questions from earlier today with real
  evidence instead of a screenshot-derived guess or a positional estimate:
  - The screen's "APN" title renders via `content-desc` on
    `com.android.settings:id/collapsing_toolbar` — **not** a plain `text`
    node as the earlier fix (based on the screenshot alone) assumed.
    `_looks_like_apn_list_screen()` corrected to check `content-desc`
    "APN" instead of `text` "APN" — the previous version would never have
    matched this actual screen.
  - The "+" button **does** have its own identifier after all: `content-desc`
    "新しい APN" ("New APN") — genuinely unambiguous, no resource-id (that
    part of the earlier guess was right: confirmed by the same dump, a
    plain `android.widget.Button` with `resource-id=""`). Its bounds,
    `[837,83][969,215]`, sit exactly adjacent to the "⋮" overflow icon's
    `[969,83][1080,215]` (sharing the x=969 edge) — this also retroactively
    confirms the position-estimate fallback added earlier today would have
    landed within ~11px of the real center (914 vs. the real 903), close
    enough it likely would have worked, but there's no need to rely on an
    estimate now. `configure_apn()` now taps `"新しい APN"` directly via
    `tap_by_content_desc()`, ahead of both `add_button_resource_id` and the
    `tap_left_of_content_desc()` fallback (which stays in the code for any
    model/screen without a captured identifier).
  - The dump also shows this screen has **no existing APN entries** at all
    under this restricted/SIM state — just the warning message — consistent
    with a genuinely blank "add new" flow, not a list to scroll through
    first.
  Still not confirmed by a live run: the dump proves what's on screen, not
  that tapping "新しい APN" actually opens the expected blank entry form.
  See `tests/test_real_shg10_fixtures.py` for the new fixture-backed tests.

### Real-device bugs found running the automation — relevant to `adb_client.py`, `main_phase2.py`
- *2026-09-08:* `config/settings.yaml`'s `adb.platform_tools_path` is a
  *directory* (`C:\platform-tools`), but was being passed straight through
  as the `adb` executable path itself. Every `AdbClient` call then failed
  with `OSError`, silently swallowed by `is_connected()` into a plain
  `False` — indistinguishable in the logs from a genuinely disconnected
  device, even though `adb devices` worked fine in a normal shell. Fixed by
  joining the directory with the executable name
  (`main_phase2._resolve_adb_path()`) and making `is_connected()` raise
  `AdbCommandError` instead of swallowing this specific failure class.
- *2026-09-08:* `subprocess.run(..., text=True, ...)` decodes `adb` output
  using the OS locale codepage — `cp932` on the client PC's Japanese-locale
  Windows install — instead of UTF-8, which is what `adb`'s actual output
  uses. Real device output (`dumpsys wifi`, containing real Wi-Fi SSIDs)
  crashed a background thread *inside* `subprocess.run()` itself, invisible
  to any `try`/`except` in this codebase, leaving `stdout=None` and
  surfacing several calls later as a confusing
  `TypeError: argument of type 'NoneType' is not iterable`. Fixed with
  explicit `encoding="utf-8", errors="replace"`. Neither of these two bugs
  was a device-data gap — both were pure code bugs that only a real
  Windows client PC with real non-ASCII device output could have surfaced;
  the fake/mock ADB layer never exercised either condition.
- *2026-09-08:* Real client-PC run showed the SHG10 test unit was already
  past OOBE (landed on a home screen, not any wizard screen) — it had been
  provisioned in an earlier session. Added `main_phase2.py --skip-wizard`
  for testing against an already-provisioned device without a fresh
  factory reset each time. Deliberately not exposed on `run_phase2_batch()`
  (the production batch path).
- *2026-09-08:* Real run also showed `wifi_setup.py`'s/`apn_setup.py`'s
  `menu_path` text navigation (tapping `設定`) fails whenever the device
  isn't already showing that text — true for `--skip-wizard` testing
  (starts from the home screen) and plausibly other real-world states too.
  Both now try the standard `android.settings.WIFI_SETTINGS` intent first
  (confirmed working — reaches the screen regardless of starting point),
  with a read-only landing check before committing to skip any menu_path
  steps, falling back to the original behavior unchanged otherwise.
- *2026-09-08:* First real run to reach APN navigation crashed with
  `[Errno 2] No such file or directory` on a local temp path, immediately
  after `apn_setup.py` logged a successful screen transition. Root cause:
  `ui_automator.dump_ui()` never checked `client.pull()`'s return value —
  when the pull silently failed (uiautomator dump is known to
  intermittently fail to produce a readable file right after a screen
  transition, which is exactly what had just happened), the code read a
  local file that was never written, crashing with a raw
  `FileNotFoundError` instead of a clear, retriable error. Fixed: `pull()`
  failure now raises `AdbCommandError` with a clear message, and the whole
  dump+pull is retried up to 3 times with a 1s delay before giving up —
  this is a well-known class of `uiautomator dump` flakiness, not specific
  to this device, so the fix is in the shared `dump_ui()` used by every
  tap/find call, not just the APN path that happened to surface it.

### Windows/client-PC environment — relevant to deployment & setup docs
- *2026-09-04:* Freshly-extracted executables on the client PC are **silently
  blocked** — scrcpy hung with no error until fixed via
  `Get-ChildItem -Path C:\scrcpy -Recurse | Unblock-File` **and** adding the
  exe to Windows Defender Firewall.
- The PC's active network is classified **Guest/Public**, and inbound
  connections for non-allowlisted apps are blocked. When adding an app via
  "Allow another app", Windows ticks **Private only by default** — Public must
  be ticked manually or the rule won't apply.
- Implication: any new executable delivered for Phase 2/3 will hit the same
  silent block on first run. Document unblock + firewall allowlist as a
  required setup step.
- Also: PowerShell requires `.\` prefix to run a local exe (unlike cmd) —
  relevant if delivered scripts assume cmd-style invocation.

---

## Dump capture status (all models)

| Model | Wi-Fi list | APN list | APN entry | APN save flow | Wizard (OOBE) |
|---|---|---|---|---|---|
| SHG10 (352063910272451) | ✅ `wifi_list_SHG10.xml` (31,516 B) | ✅ `apn_restricted_SHG10.xml` (6,104 B) | ✅ `apn_entry_top_SHG10.xml` (17,785 B), `apn_entry_middle_SHG10.xml` (21,981 B), `apn_entry_bottom_SHG10.xml` (20,608 B), `apn_entry_filled_SHG10.xml` (21,988 B) | ✅ `apn_overflow_menu_SHG10.xml` (3,839 B), `apn_mcc_validation_SHG10.xml` (5,085 B), `apn_mnc_validation_SHG10.xml` (5,092 B) | ❌ **not obtainable remotely** — see constraint analysis below. Photos only. |
| Xperia Ace III (SOG08) | ❌ not started | ❌ not started | ❌ not started | ❌ not started | ❌ same constraint applies |
| Xperia 10 IV (SOG07) | ❌ not started | ❌ not started | ❌ not started | ❌ not started | ❌ same constraint applies |
| AQUOS sense6s (SHG07) | ❌ not started | ❌ not started | ❌ not started | ❌ not started | ❌ same constraint applies |

Original 4 SHG10 files captured 2026-09-04. 4 more (save flow + a filled
entry form) captured 2026-09-08, same session as the Save flow findings
above. `apn_restricted_SHG10.xml` (the APN *list* screen itself — the
piece missing from every earlier capture, which only ever reached the edit
*form*) added 2026-09-11 — see the dated entry above for what it resolved.

Capture pattern used:
```
adb -s <serial> shell uiautomator dump /sdcard/<name>.xml
adb -s <serial> pull /sdcard/<name>.xml <name>_<MODEL>.xml
```
Files collected in `C:\scrcpy\dumps` on the client PC; destined for
`tests/fixtures/` in the repo via git.

---

## Wizard capture — RESOLVED AS NOT REMOTELY POSSIBLE (2026-09-08)

**Status: all remote methods exhausted. Do not re-test these.**

### The real OOBE sequence (confirmed by client photos, 2026-09-08)

The client factory-reset the unit and photographed every screen. Confirmed
order:

1. SHARP logo → AQUOS logo → SIM/microSD tray warning screen
2. **「ようこそ」** — language (日本語(日本)), 視覚補助, start button
3. **「キャリア設定中」** — carrier config spinner (carrier-injected)
4. **「Wi-Fiに接続」** — 「すべてのWi-Fiネットワークを表示」/「新しいネットワーク
   を追加」/「設定時にモバイルネットワークを使用」, **「オフラインで設定」**
   bottom-left
5. **「オフラインで設定しますか?」** dialog — 戻る / 続行
6. **「セットアップを続けますか?」** — 続行 /「中断し、リマインダーを受け取る」
7. Google services / terms (scrollable) → 「同意する」
8. **「ソフトウェア更新について」** — SHARP-specific
9. **「スマートフォンを設定しています」** — provisioning spinner
10. **「AQUOS Homeの通知アクセス」** — SHARP-specific dialog, OK
11. Home screen

**Key finding — account sign-in is NOT a blocking screen.** The client took
the 「オフラインで設定」 path and Google account login never appeared. This
matches the client's real workflow (manual login ~5 days after
initialization). `wizard_walkthrough.py` likely only needs the offline path.
**Confirm with client that offline-setup is standard for all devices** — it
substantially narrows what needs automating.

### Confirmed reset menu path (SHARP skin)
**設定 → システム → リセット オプション → すべてのデータを消去（初期設定に
リセット）→ すべてのデータを消去** (confirm dialog 「すべてのデータを消去
しますか?」).
Note: **開発者向けオプション sits directly above リセット オプション under
システム** on this model — not a top-level item.

### Why remote dumping is impossible — 4 methods tested, all failed

| # | Method | Result |
|---|---|---|
| 1 | `settings put global device_provisioned 0` + `user_setup_complete 0` + reboot | Flags accepted, but SHARP's build ignores them — boots straight to home screen. Tried twice. |
| 2 | `am start com.google.android.setupwizard/.deferred.DeferredSetupWizardActivity` | `SecurityException: Permission Denial ... requires com.google.android.setupwizard.SETUP`. `SETUP` is a **signature-level** permission — cannot be granted via `pm grant`, no non-root workaround. (XDA reports of this working are Android 10–13; A14 tightened it.) |
| 3 | `am start` on SHARP's `jp.co.sharp.android.setupwizard` activities | **No SecurityException** — SHARP's package is not permission-guarded. But every activity exits silently without rendering. Tried: `CheckDeferrendSetupActivity`, `GotaConsentToUseActivity`, `GmsSetupWizardActivity`, `SettingDefaultHomeActivity`, `SkipFaceUnlockActivity`. |
| 4 | Flags at `0` **combined with** activity launch (the untested gap) | Flags verified as `0`, nav bar lost home/recents buttons (system genuinely treated device as unprovisioned) — but **「Androidの設定」が繰り返し停止しています**: Settings entered a crash loop. No wizard. Had to restore flags + reboot to recover. |

**Structural reason:** `WizardManagerActivity` orchestrates the flow and only
runs at genuine first boot. Individual activities check state, find setup
complete, and exit. Forcing the state destabilizes the system rather than
re-entering the flow.

**And the deeper constraint:** even a real factory reset doesn't help, because
the reset wipes ADB authorization. `uiautomator dump` requires ADB. From wipe
until someone manually re-enables USB debugging and taps 「許可」 on-device,
there is no ADB channel — and by then the device has reached the home screen
and the wizard is gone. ADB access and wizard visibility cannot coexist.

### Discovered activity names (useful for detection logic even without ids)

`jp.co.sharp.android.setupwizard/` — `SettingDefaultHomeActivity`,
`GotaConsentToUseActivity` (likely 「ソフトウェア更新について」),
`CheckDeferrendSetupActivity`, `GmsSetupWizardActivity`,
`SkipFaceUnlockActivity`, `CheckBYODActivity`

`com.google.android.setupwizard/` — `WizardManagerActivity`,
`user.WelcomeActivity` (=「ようこそ」), `user.GestureIntroActivity`,
`carrier.SlotsSelectionActivity`, `carrier.MobileDataActivity`
(=「キャリア設定中」), `update.OtaUpdateActivity`,
`provision.*`, `portal.PortalProgressActivity`, `restore.GetRestoreFlowActivity`

### Chosen approach for `wizard_walkthrough.py`
1. Build navigation logic from the photographed screen order above — order,
   labels, and button positions are all known.
2. Use standard Google SetupWizardLib ids as best guesses, tagged
   **`TODO(real-device, best-guess-standard-id)`** to distinguish "probably
   right, unverified" from "pure placeholder".
3. **Fail loudly** on a missed match rather than tapping blindly — consistent
   with the existing `AmbiguousResourceIdError` philosophy, and important
   given the USB-debugging-disable notification hazard.
4. Resolve real ids during Phase 2 on-site testing: the walkthrough will fail
   at the first mismatched screen and log which one, replacing placeholders
   device by device. This costs nothing extra — it happens during testing
   that's needed anyway.

**Caveat on standard ids:** screens 3, 8, and 10 above are SHARP/carrier-
specific and will NOT match generic SetupWizardLib ids. Expect these to need
resolution via method 4. Also expect the sequence to differ on the Xperia
models.

### Operational note for Phase 2/3
`adb shell svc power stayon usb` prevents screen timeout while cabled. Devices
sitting idle mid-workflow would otherwise sleep and interrupt UI automation —
worth doing as part of device prep in the orchestration layer.

---

## IMPLEMENTATION SPEC — wizard via text matching (2026-09-08)

Everything below is code-ready. Derived from the client's screen photos, so
**visible text is known and reliable; resource-ids are not available.**

### Why text matching, not resource-ids

A resource-id (e.g. `com.google.android.setupwizard:id/start_button`) is an
internal view-hierarchy identifier. It is **never rendered on screen**, so no
photo of any quality contains it. `uiautomator dump` reads it via the
accessibility layer, which needs ADB — unavailable during OOBE (see constraint
analysis above).

Visible **text labels** are in the photos, and `ui_automator.py` already has
`find_by_text` / `tap_by_text` (added in Stage A for Settings menu
navigation). So the wizard is driven by text where labels are unique, with
best-guess ids only as fallback.

### Per-screen strings (SHG10, offline path)

| # | Screen identifier text | Action target text | Notes |
|---|---|---|---|
| 1 | (SIM/microSD tray warning) | — | Transient; may auto-dismiss. Treat as skippable. |
| 2 | `ようこそ` | (start button) | **Button label not legible in photo — needs verification.** Language already 日本語(日本) by default. |
| 3 | `キャリア設定中` | — | Spinner, no interaction. Wait-for-disappear. |
| 4 | `Wi-Fiに接続` | `オフラインで設定` | Bottom-left. **This is the branch point** that keeps the flow offline. |
| 5 | `オフラインで設定しますか?` | `続行` | Dialog. Other button is `戻る` — do NOT tap. |
| 6 | `セットアップを続けますか?` | `続行` | Other button is `中断し、リマインダーを受け取る` — do NOT tap. |
| 7 | (Google services / terms) | `同意する` | **Scrollable** — may need scroll-to-bottom before the button is reachable. |
| 8 | `ソフトウェア更新について` | (confirm button) | SHARP-specific. **Button label not legible in photo — needs verification.** |
| 9 | `スマートフォンを設定しています` | — | Spinner, no interaction. Wait-for-disappear. |
| 10 | `AQUOS Homeの通知アクセス` | `OK` | SHARP-specific dialog. |
| 11 | (home screen) | — | Terminal state — detect and exit. |

**Unverified items (flag as TODO in code):** screens 2 and 8 button labels.
The photos show the buttons but the text is not readable. Either confirm with
the client on the next reset, or match by position/index as a fallback.

### Proposed YAML schema addition

```yaml
wizard:
  screens:
    - name: welcome
      identify_by_text: "ようこそ"
      action: tap_by_text
      target_text: "開始"        # TODO(verify) — not legible in photo
    - name: carrier_setup
      identify_by_text: "キャリア設定中"
      action: wait_for_disappear
      timeout_sec: 120
    - name: wifi_connect
      identify_by_text: "Wi-Fiに接続"
      action: tap_by_text
      target_text: "オフラインで設定"
    - name: offline_confirm
      identify_by_text: "オフラインで設定しますか?"
      action: tap_by_text
      target_text: "続行"
    - name: continue_setup
      identify_by_text: "セットアップを続けますか?"
      action: tap_by_text
      target_text: "続行"
    - name: google_terms
      identify_by_text: "同意する"
      action: scroll_then_tap_by_text
      target_text: "同意する"
    - name: software_update
      identify_by_text: "ソフトウェア更新について"
      action: tap_by_text
      target_text: "TODO(verify)"
    - name: provisioning
      identify_by_text: "スマートフォンを設定しています"
      action: wait_for_disappear
      timeout_sec: 300
    - name: aquos_notify
      identify_by_text: "AQUOS Homeの通知アクセス"
      action: tap_by_text
      target_text: "OK"
```

### Design requirements for `wizard_walkthrough.py`

- **Screen-driven, not sequence-driven.** Identify which screen is present by
  text, then act. Do not assume a fixed order — carrier/OTA screens may appear
  conditionally depending on network state.
- **Fail loudly on unrecognized screens.** Log the full text content of the
  unknown screen so the label can be added to config. Never tap blindly.
  Consistent with the existing `AmbiguousResourceIdError` philosophy.
- **Never tap near the USB-debugging notification** (see UI hazard section) —
  a mistap disables ADB and strands the device.
- **Spinner screens need wait-for-disappear, not tap.** Screens 3 and 9.
- **The 「戻る」/「中断」 buttons must never be tapped** — they reverse or abort
  the flow. Explicitly exclude these strings from any fuzzy matching.
- Text matching should be exact or prefix-based, not substring — 「続行」
  appears on multiple screens and must be disambiguated by the screen
  identifier, not matched globally.

### Screenshot storage (reference material, not test fixtures)

Photos are **not** test fixtures (no test parses them). Store under docs:

```
docs/
├── record.md
└── screens/
    └── shg10/
        └── wizard/
            ├── 01_welcome.jpg
            ├── 02_carrier_setup.jpg
            ├── 03_wifi_connect.jpg
            ├── 04_offline_confirm.jpg
            ├── 05_continue_setup.jpg
            ├── 06_google_terms.jpg
            ├── 07_software_update.jpg
            ├── 08_provisioning.jpg
            └── 09_aquos_notify.jpg
```

Numbering matches the sequence above so the two cross-reference.

**Privacy caution before committing:** several client photos show clear
reflections of the person holding the camera in the phone's screen. Crop
before committing, or keep the photos out of git entirely and rely on this
file's text description.

---

## Overall status (as of 2026-09-08, end of day)

- **Stage A: complete.** All config YAMLs, `src/device/`, `src/phase2/`,
  `src/orchestration/`, `src/main_phase2.py`, plus `PENDING_REAL_DEVICE_DATA.md`
  and `README.md`. Test suite has grown well past the original 30 as Stage B
  work landed (110 passing as of this entry, still ~1s, no real device needed).
- **Stage B for SHG10: Wi-Fi and APN (including Save) resolved and tested
  against real captures.** Wizard remains on the photograph-derived
  screen-driven config, blocked only on the two button labels noted above —
  everything else about it is implemented and tested.
- **Completed since the "ready to start" entry above:**
  1. ✅ 8 real dumps now in `tests/fixtures/` (the original 4 plus
     `apn_overflow_menu_SHG10.xml`, `apn_mcc_validation_SHG10.xml`,
     `apn_mnc_validation_SHG10.xml`, `apn_entry_filled_SHG10.xml`).
  2. ✅ `PENDING_REAL_DEVICE_DATA.md` updated with real SSID pairs, then
     updated again as Save/MCC/MNC resolved.
  3. ✅ Wi-Fi + APN resource-ids resolved and tested (`tests/test_real_shg10_fixtures.py`,
     `tests/test_wifi_setup.py`, `tests/test_apn_setup.py`).
  4. ✅ MCC/MNC confirmed mandatory; Save flow fully resolved (two-tap
     overflow menu, sequential blocking validation) — see the APN settings
     section above.
  5. ⏳ `wizard_walkthrough.py` built (screen-driven, text-matching,
     best-guess ids where needed) — implemented and tested, but 2 of 9
     screens' button labels are still unverified, so a real end-to-end
     wizard run hasn't happened yet.
  6. ⏳ Still not confirmed with the client: is 「オフラインで設定」 standard
     for all devices?
  7. ⏳ Not started: dump capture for SOG08/SOG07/SHG07.
- **New since this entry started:** real hardware surfaced two pure code
  bugs (adb path resolution, UTF-8 decoding — see "Real-device bugs" above)
  neither of which was a device-data gap; both are fixed. Also added
  `--skip-wizard` (testing convenience) and the `WIFI_SETTINGS` intent
  navigation shortcut (robustness improvement, not device-data).
- **Actual current blocker for a full SHG10 run:** real Wi-Fi credentials —
  see "Highest priority" in `PENDING_REAL_DEVICE_DATA.md`. Everything else
  in the Wi-Fi → APN chain is implemented, tested, and has gotten as far as
  it can without a real network to join.
- **Schema note (carried from Stage A, now fully resolved for SHG10):** the
  6 fields added in Stage A plus several more added during Stage B are all
  documented in `PENDING_REAL_DEVICE_DATA.md`'s "Schema additions" section.
  MCC/MNC turned out to exist and be mandatory (not absent, as an earlier
  entry above speculated) — see the APN settings section.

---

## Template for a new device section

## <MODEL> (<manufacturer>, <carrier branding>, Android <version>)

**Serial:**
**Confirmed identity string (from adb):**

### Test Log — exactly what was run against this unit

| Date | Test | Command | Result |
|---|---|---|---|
| | | | |

### <Category> — relevant to `<file or component>`
- *<date>:* <what was observed>
- Implication: <why it matters for the code/config>
